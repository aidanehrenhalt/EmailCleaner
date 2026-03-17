"""CLI entry point and orchestration."""

import argparse
import sys

from rich.console import Console

from emailcleaner import __version__
from emailcleaner.auth import get_gmail_service
from emailcleaner.gmail import (
    list_message_ids,
    get_message_headers,
    batch_trash,
    batch_delete,
)
from emailcleaner.grouping import group_by_domain
from emailcleaner.display import (
    show_summary,
    write_csv,
    prompt_selection,
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
        "--include-receipts",
        action="store_true",
        help="Include transactional emails (receipts, purchases, shipping, payments) in sender counts (excluded by default)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write results to a CSV file instead of displaying interactively (e.g. results.csv)",
    )
    return parser


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

    # --- Group by domain ---
    groups = group_by_domain(
        messages,
        min_count=args.min_count,
        exclude_receipts=not args.include_receipts,
    )

    if args.output:
        write_csv(groups, args.output, sort_by=args.sort)
        if args.dry_run:
            sys.exit(0)
    else:
        show_summary(groups, sort_by=args.sort)

    if args.dry_run:
        console.print("\n[dim]Dry run — no changes made.[/dim]")
        sys.exit(0)

    if not groups:
        sys.exit(0)

    # --- Select and clean ---
    if args.domains:
        # Non-interactive mode
        target_domains = {d.strip().lower() for d in args.domains.split(",")}
        selected = [g for g in groups.values() if g.domain in target_domains]
        if not selected:
            console.print(
                f"[yellow]None of the specified domains found: {args.domains}[/yellow]"
            )
            sys.exit(1)
    else:
        selected = prompt_selection(groups)

    if not selected:
        console.print("[dim]Nothing selected. Exiting.[/dim]")
        sys.exit(0)

    action = "delete" if args.delete else "trash"
    if not confirm_action(selected, action=action):
        console.print("[dim]Cancelled.[/dim]")
        sys.exit(0)

    # --- Execute ---
    all_ids = []
    for g in selected:
        all_ids.extend(g.message_ids)

    action_fn = batch_delete if args.delete else batch_trash
    action_verb = "Deleting" if args.delete else "Trashing"

    with make_progress() as progress:
        task = progress.add_task(f"{action_verb}...", total=len(all_ids))
        processed = action_fn(service, all_ids)
        progress.update(task, completed=processed)

    past_tense = "deleted" if args.delete else "trashed"
    console.print(
        f"\n[bold green]Done! {processed} emails {past_tense}.[/bold green]"
    )
