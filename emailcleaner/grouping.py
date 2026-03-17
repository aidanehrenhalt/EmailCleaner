"""Sender domain extraction, normalization, and grouping."""

import dataclasses
import email.utils

import tldextract


@dataclasses.dataclass
class SenderGroup:
    """A cluster of emails from the same organizational domain."""

    domain: str
    raw_domains: set[str] = dataclasses.field(default_factory=set)
    sender_addresses: set[str] = dataclasses.field(default_factory=set)
    message_ids: list[str] = dataclasses.field(default_factory=list)
    subjects: list[str] = dataclasses.field(default_factory=list)
    count: int = 0


def extract_email_address(from_header: str) -> str:
    """Parse 'Display Name <user@example.com>' -> 'user@example.com'."""
    _, addr = email.utils.parseaddr(from_header)
    return addr.lower()


def normalize_domain(email_addr: str) -> str:
    """Extract the registered domain from an email address.

    Examples:
        user@email.amazon.com -> amazon.com
        user@bounce.twitter.com -> twitter.com
        user@news.bbc.co.uk -> bbc.co.uk
    """
    if "@" not in email_addr:
        return email_addr
    domain = email_addr.split("@", 1)[1]
    extracted = tldextract.extract(domain)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    return domain


def group_by_domain(
    messages: list[dict], min_count: int = 1
) -> dict[str, SenderGroup]:
    """Group messages by normalized sender domain.

    Args:
        messages: List of dicts with keys: id, from_header, subject.
        min_count: Minimum emails from a domain to include in results.

    Returns:
        Dict mapping normalized domain -> SenderGroup, sorted by count desc.
    """
    groups: dict[str, SenderGroup] = {}

    for msg in messages:
        addr = extract_email_address(msg["from_header"])
        if not addr:
            continue

        domain = normalize_domain(addr)
        raw_domain = addr.split("@", 1)[1] if "@" in addr else addr

        if domain not in groups:
            groups[domain] = SenderGroup(domain=domain)

        g = groups[domain]
        g.raw_domains.add(raw_domain)
        g.sender_addresses.add(addr)
        g.message_ids.append(msg["id"])
        g.count += 1

        # Keep up to 5 unique example subjects
        subj = msg.get("subject", "(no subject)")
        if len(g.subjects) < 5 and subj not in g.subjects:
            g.subjects.append(subj)

    # Filter by min_count and sort by count descending
    filtered = {
        k: v for k, v in groups.items() if v.count >= min_count
    }
    return dict(
        sorted(filtered.items(), key=lambda item: item[1].count, reverse=True)
    )
