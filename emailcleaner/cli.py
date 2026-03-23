"""CLI entry point and orchestration."""

import argparse
import sys
from datetime import datetime

from rich.console import Console

from emailcleaner import __version__
from emailcleaner.auth import get_gmail_service
from emailcleaner.gmail import (
    list_message_ids,
    get_message_headers,
    list_labels,
    batch_apply_label,
    batch_trash,
    batch_delete,
)
from emailcleaner.grouping import group_by_domain, is_transactional
from emailcleaner.display import (
    write_csv,
    write_label_csv,
    paginated_select,
    confirm_action,
    make_progress,
    console,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emailcleaner",
        description="Bulk-clean marketing emails from Gmail",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Path to OAuth2 client secrets JSON (default: credentials.json)",
    )
    parser.add_argument(
        "--token-dir",
        default=None,
        help="Directory to store auth token (default: ~/.emailcleaner/)",
    )
    parser.add_argument(
        "-q",
        "--query",
        default="",
        help='Gmail search query (e.g. "category:promotions", "is:unread")',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and display only, do not modify emails",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Permanently delete instead of trashing (requires confirmation)",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=2,
        help="Only show senders with at least N emails (default: 2)",
    )
    parser.add_argument(
        "--sort",
        choices=["count", "domain"],
        default="count",
        help="Sort summary by count or domain (default: count)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max number of messages to scan (0 = unlimited)",
    )
    parser.add_argument(
        "--domains",
        default=None,
        help="Comma-separated domains to clean (non-interactive mode)",
    )
    parser.add_argument(
        "--label",
        default=None,
        metavar="LABEL_NAME",
        help='Apply a Gmail label to all matched emails (e.g. "Internship / Job Hunting"). '
             "Skips interactive sender selection.",
    )
    parser.add_argument(
        "--include-receipts",
        action="store_true",
        help="Include transactional emails (receipts, purchases, shipping, payments) in sender counts (excluded by default)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="CSV output filename (default: junk_senders.csv or labeled_emails.csv)",
    )
    parser.add_argument(
        "--new-file",
        action="store_true",
        help="Write to a new timestamped CSV instead of overwriting the default file",
    )
    parser.add_argument(
        "--whoami",
        action="store_true",
        help="Print the email address associated with the current token and exit",
    )
    return parser


def _resolve_output(output_arg: str | None, new_file: bool, default: str) -> str:
    """Return the CSV path to write to.

    - Custom name via --output wins if provided.
    - --new-file inserts a timestamp before the .csv extension.
    - Otherwise the default filename is used (overwriting if it exists).
    """
    base = output_arg or default
    if new_file:
        stem, _, ext = base.rpartition(".")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{stem}_{ts}.{ext}" if stem else f"{base}_{ts}"
    return base


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Authenticate ---
    console.print("[bold]Authenticating with Gmail...[/bold]")
    try:
        kwargs = {"credentials_path": args.credentials, "full_access": args.delete}
        if args.token_dir:
            kwargs["token_dir"] = args.token_dir
        service = get_gmail_service(**kwargs)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        sys.exit(1)

    console.print("[green]Authenticated.[/green]\n")

    if args.whoami:
        profile = service.users().getProfile(userId="me").execute()
        console.print(f"Signed in as: [bold cyan]{profile['emailAddress']}[/bold cyan]")
        console.print(f"Token dir:    {args.token_dir or '~/.emailcleaner/'}")
        sys.exit(0)

    # --- Scan messages ---
    query_display = args.query or "(all mail)"
    console.print(f"[bold]Scanning emails matching:[/bold] {query_display}")

    with make_progress() as progress:
        scan_task = progress.add_task("Listing messages...", total=None)
        message_ids = []
        for msg_id in list_message_ids(
            service, query=args.query, limit=args.limit
        ):
            message_ids.append(msg_id)
            progress.update(scan_task, description=f"Found {len(message_ids)} messages...")

    if not message_ids:
        console.print("[yellow]No messages found.[/yellow]")
        sys.exit(0)

    console.print(f"Found [bold]{len(message_ids)}[/bold] messages. Fetching headers...\n")

    # --- Fetch headers ---
    with make_progress() as progress:
        fetch_task = progress.add_task("Fetching headers...", total=len(message_ids))

        def on_batch(fetched, total):
            progress.update(fetch_task, completed=fetched)

        messages = get_message_headers(
            service, message_ids, on_batch_done=on_batch
        )

    # --- Label mode: apply a label to all matched emails and exit ---
    if args.label:
        labels = list_labels(service)
        label_id = labels.get(args.label)
        if not label_id:
            console.print(f"[red]Label '{args.label}' not found.[/red]")
            console.print(
                "Available labels: "
                + ", ".join(sorted(labels.keys()))
            )
            sys.exit(1)

        label_messages = [
            msg for msg in messages
            if args.include_receipts or not is_transactional(msg.get("subject", ""))
        ]

        csv_path = _resolve_output(args.output, args.new_file, "labeled_emails.csv")

        if args.dry_run:
            console.print(
                f"\n[dim]Dry run — would label {len(label_messages)} emails "
                f"→ '{args.label}' and save to {csv_path}[/dim]"
            )
            sys.exit(0)

        with make_progress() as progress:
            task = progress.add_task("Applying label...", total=len(label_messages))
            processed = batch_apply_label(service, [m["id"] for m in label_messages], label_id)
            progress.update(task, completed=processed)

        write_label_csv(label_messages, csv_path, args.label)
        console.print(
            f"\n[bold green]Done! {processed} emails labeled "
            f"→ '{args.label}'[/bold green]"
        )
        sys.exit(0)

    # --- Group by domain ---
    groups = group_by_domain(
        messages,
        min_count=args.min_count,
        exclude_receipts=not args.include_receipts,
    )

    csv_path = _resolve_output(args.output, args.new_file, "junk_senders.csv")
    write_csv(groups, csv_path, sort_by=args.sort)

    if args.dry_run:
        console.print("\n[dim]Dry run — no changes made.[/dim]")
        sys.exit(0)

    if not groups:
        sys.exit(0)

    action = "delete" if args.delete else "trash"
    action_fn = batch_delete if args.delete else batch_trash
    action_verb = "Deleting" if args.delete else "Trashing"
    past_tense = "deleted" if args.delete else "trashed"

    # --- Non-interactive mode: single pass ---
    if args.domains:
        target_domains = {d.strip().lower() for d in args.domains.split(",")}
        selected = [g for g in groups.values() if g.domain in target_domains]
        if not selected:
            console.print(
                f"[yellow]None of the specified domains found: {args.domains}[/yellow]"
            )
            sys.exit(1)

        if not confirm_action(selected, action=action):
            console.print("[dim]Cancelled.[/dim]")
            sys.exit(0)

        all_ids = []
        for g in selected:
            all_ids.extend(g.message_ids)

        with make_progress() as progress:
            task = progress.add_task(f"{action_verb}...", total=len(all_ids))
            processed = action_fn(service, all_ids)
            progress.update(task, completed=processed)

        console.print(
            f"\n[bold green]Done! {processed} emails {past_tense}.[/bold green]"
        )
        sys.exit(0)

    # --- Interactive loop: select, clean, repeat ---
    while groups:
        selected = paginated_select(groups, sort_by=args.sort)
        if not selected:
            console.print("[dim]Exiting.[/dim]")
            sys.exit(0)

        if not confirm_action(selected, action=action):
            console.print("[dim]Skipped.[/dim]")
            continue

        all_ids = []
        for g in selected:
            all_ids.extend(g.message_ids)

        with make_progress() as progress:
            task = progress.add_task(f"{action_verb}...", total=len(all_ids))
            processed = action_fn(service, all_ids)
            progress.update(task, completed=processed)

        console.print(
            f"\n[bold green]Done! {processed} emails {past_tense}.[/bold green]"
        )

        # Remove cleaned groups so the next iteration shows what's left
        for g in selected:
            groups.pop(g.domain, None)

        if not groups:
            console.print("\n[bold]All sender groups have been cleaned.[/bold]")
            break

        # Pause so the user can see the result before redisplaying
        try:
            input("\nPress Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
