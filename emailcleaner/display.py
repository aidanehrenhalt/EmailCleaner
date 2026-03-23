"""Terminal display: summary tables, selection prompts, and progress."""

import csv
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from emailcleaner.grouping import SenderGroup

console = Console()


_PAGE_SIZES = [10, 25, 50]


def show_summary(
    groups: dict[str, SenderGroup],
    sort_by: str = "count",
    page: int = 1,
    page_size: int = 0,
):
    """Print a table summarizing sender groups.

    Args:
        page: Current page (1-indexed). Ignored when page_size is 0.
        page_size: Groups per page. 0 shows all groups (no pagination).
    """
    if not groups:
        console.print("[yellow]No emails found matching your criteria.[/yellow]")
        return

    sorted_groups = list(groups.values())
    if sort_by == "domain":
        sorted_groups.sort(key=lambda g: g.domain)
    # Default is already sorted by count from grouping.py

    total_count = len(sorted_groups)
    total_emails = sum(g.count for g in sorted_groups)

    if page_size > 0:
        total_pages = max(1, -(-total_count // page_size))
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = min(start + page_size, total_count)
        display_groups = sorted_groups[start:end]
        title = f"Email Sender Summary (page {page} of {total_pages})"
    else:
        start = 0
        display_groups = sorted_groups
        title = "Email Sender Summary"

    table = Table(title=title, show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Domain", style="cyan", min_width=20)
    table.add_column("Count", style="magenta", justify="right", width=7)
    table.add_column("Sender Addresses", style="green", max_width=40)
    table.add_column("Example Subjects", style="white", max_width=50)

    for i, group in enumerate(display_groups, start + 1):
        addrs = "\n".join(sorted(group.sender_addresses)[:3])
        if len(group.sender_addresses) > 3:
            addrs += f"\n(+{len(group.sender_addresses) - 3} more)"

        subjects = "\n".join(group.subjects[:3])
        if len(group.subjects) > 3:
            subjects += f"\n..."

        table.add_row(str(i), group.domain, str(group.count), addrs, subjects)

    console.print(table)

    if page_size > 0:
        console.print(
            f"\n[bold]{total_count}[/bold] sender groups, "
            f"[bold]{total_emails}[/bold] total emails "
            f"(showing {start + 1}\u2013{start + len(display_groups)})"
        )
    else:
        console.print(
            f"\n[bold]{total_count}[/bold] sender groups, "
            f"[bold]{total_emails}[/bold] total emails"
        )


def write_csv(groups: dict[str, SenderGroup], path: str, sort_by: str = "count"):
    """Write sender groups to a CSV file."""
    sorted_groups = list(groups.values())
    if sort_by == "domain":
        sorted_groups.sort(key=lambda g: g.domain)

    output = Path(path)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["domain", "count", "sender_addresses", "example_subjects"])
        for group in sorted_groups:
            addrs = "; ".join(sorted(group.sender_addresses))
            subjects = "; ".join(group.subjects)
            writer.writerow([group.domain, group.count, addrs, subjects])

    console.print(f"\n[green]Saved {len(sorted_groups)} sender groups to[/green] {output}")


def write_label_csv(messages: list[dict], path: str, label_name: str):
    """Write labeled messages to a CSV file."""
    output = Path(path)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "from", "subject", "date"])
        for msg in messages:
            writer.writerow([
                label_name,
                msg.get("from_header", ""),
                msg.get("subject", ""),
                msg.get("date", ""),
            ])
    console.print(f"\n[green]Saved {len(messages)} labeled emails to[/green] {output}")


def prompt_selection(groups: dict[str, SenderGroup]) -> list[SenderGroup]:
    """Prompt the user to select sender groups by index.

    Supports: individual numbers (1,3,5), ranges (1-10), 'all', or 'q' to quit.
    """
    group_list = list(groups.values())
    console.print(
        "\n[bold]Select sender groups to clean:[/bold]"
        "\n  Enter numbers (e.g. [cyan]1,3,5[/cyan]), "
        "ranges (e.g. [cyan]1-10[/cyan]), [cyan]all[/cyan], or [cyan]q[/cyan] to quit."
    )

    while True:
        try:
            raw = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []

        if raw in ("q", "quit", "exit"):
            return []

        if raw == "all":
            return group_list

        selected_indices = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-", 1)
                    for idx in range(int(start), int(end) + 1):
                        selected_indices.add(idx)
                else:
                    selected_indices.add(int(part))
        except ValueError:
            console.print("[red]Invalid input. Use numbers, ranges, 'all', or 'q'.[/red]")
            continue

        # Validate indices
        valid = [i for i in selected_indices if 1 <= i <= len(group_list)]
        if not valid:
            console.print(
                f"[red]No valid indices. Enter numbers between 1 and {len(group_list)}.[/red]"
            )
            continue

        return [group_list[i - 1] for i in sorted(valid)]


def paginated_select(
    groups: dict[str, SenderGroup],
    sort_by: str = "count",
    page_size: int = 10,
) -> list[SenderGroup]:
    """Paginated interactive browser for selecting sender groups to clean.

    Navigation: n/next, p/prev, first, last, page N, size 10|25|50.
    Selection: numbers (1,3,5), ranges (1-10), all, q to quit.
    """
    sorted_groups = list(groups.values())
    if sort_by == "domain":
        sorted_groups.sort(key=lambda g: g.domain)

    total = len(sorted_groups)
    page = 1

    while True:
        total_pages = max(1, -(-total // page_size))
        page = max(1, min(page, total_pages))

        show_summary(groups, sort_by=sort_by, page=page, page_size=page_size)

        # Navigation hints
        nav_parts = []
        if total_pages > 1:
            nav_parts.append("[cyan]n[/cyan]ext")
            nav_parts.append("[cyan]p[/cyan]rev")
            nav_parts.append("[cyan]first[/cyan]")
            nav_parts.append("[cyan]last[/cyan]")
            nav_parts.append("[cyan]page[/cyan] N")
        nav_parts.append(
            f"[cyan]size[/cyan] {'/'.join(str(s) for s in _PAGE_SIZES)}"
        )
        console.print(f"  {' | '.join(nav_parts)}")

        console.print(
            "\n[bold]Select sender groups to clean:[/bold]"
            "\n  Enter numbers (e.g. [cyan]1,3,5[/cyan]), "
            "ranges (e.g. [cyan]1-10[/cyan]), [cyan]all[/cyan], "
            "or [cyan]q[/cyan] to quit."
        )

        try:
            raw = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return []

        if raw in ("q", "quit", "exit"):
            return []

        # --- Navigation commands ---
        if raw in ("n", "next"):
            if page < total_pages:
                page += 1
            else:
                console.print("[dim]Already on the last page.[/dim]")
            continue

        if raw in ("p", "prev"):
            if page > 1:
                page -= 1
            else:
                console.print("[dim]Already on the first page.[/dim]")
            continue

        if raw == "first":
            page = 1
            continue

        if raw == "last":
            page = total_pages
            continue

        if raw.startswith("page "):
            try:
                target = int(raw.split(None, 1)[1])
                if 1 <= target <= total_pages:
                    page = target
                else:
                    console.print(
                        f"[red]Page must be between 1 and {total_pages}.[/red]"
                    )
            except (ValueError, IndexError):
                console.print("[red]Usage: page N[/red]")
            continue

        if raw.startswith("size "):
            try:
                new_size = int(raw.split(None, 1)[1])
                if new_size in _PAGE_SIZES:
                    page_size = new_size
                    page = 1
                else:
                    console.print(
                        f"[red]Size must be one of: "
                        f"{', '.join(str(s) for s in _PAGE_SIZES)}[/red]"
                    )
            except (ValueError, IndexError):
                console.print("[red]Usage: size N[/red]")
            continue

        # --- Selection ---
        if raw == "all":
            return sorted_groups

        selected_indices = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    start_s, end_s = part.split("-", 1)
                    for idx in range(int(start_s), int(end_s) + 1):
                        selected_indices.add(idx)
                else:
                    selected_indices.add(int(part))
        except ValueError:
            console.print(
                "[red]Invalid input. Use numbers, ranges, "
                "navigation commands, 'all', or 'q'.[/red]"
            )
            continue

        valid = [i for i in selected_indices if 1 <= i <= total]
        if not valid:
            console.print(
                f"[red]No valid indices. "
                f"Enter numbers between 1 and {total}.[/red]"
            )
            continue

        return [sorted_groups[i - 1] for i in sorted(valid)]


def confirm_action(selected: list[SenderGroup], action: str = "trash") -> bool:
    """Show what will happen and ask for confirmation."""
    total = sum(g.count for g in selected)
    domains = ", ".join(g.domain for g in selected[:5])
    if len(selected) > 5:
        domains += f", ... (+{len(selected) - 5} more)"

    console.print(f"\n[bold yellow]About to {action} {total} emails[/bold yellow]")
    console.print(f"  From: {domains}")
    if action == "trash":
        console.print("  [dim](Trashed emails can be recovered for 30 days)[/dim]")
    else:
        console.print("  [bold red]WARNING: Permanent deletion cannot be undone![/bold red]")

    try:
        answer = input(f"\nProceed? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    return answer in ("y", "yes")


def make_progress():
    """Create a Rich progress bar for batch operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    )
