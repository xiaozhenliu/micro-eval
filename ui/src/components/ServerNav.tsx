import Link from "next/link";

const NAV_ITEMS = [
  { label: "Workspaces", href: "/workspaces" },
  { label: "Queue", href: "/queue" },
  { label: "Templates", href: "/templates" },
];

export function ServerNav() {
  return (
    <nav className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-4">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="text-sm text-neutral-400 hover:text-neutral-100 transition-colors"
          >
            {item.label}
          </Link>
        ))}
      </div>
      {/* Identity slot — filled by Task 13 MemberIdentity component */}
      <div id="member-identity-slot" />
    </nav>
  );
}
