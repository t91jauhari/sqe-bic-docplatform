"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  LayoutDashboard,
  Inbox,
  Layers,
  FileCheck2,
  Settings,
  Upload,
  LogOut,
  ArrowUpRight,
  ShieldCheck,
  WifiOff,
} from "lucide-react";
import { usePlatform, useData } from "./platform-provider";
import { Busy } from "./ui";
import { ToastNotifications } from "./toast-notifications";
import type { Dashboard, Branch, RolePermissionsMap } from "@/lib/types";
import { WorkspaceControls } from "./workspace-controls";
import { pageIdentity, PagePath } from "./page-identity";

const nav: {
  id: string;
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  gloss?: string;
}[] = [
  { id: "overview", href: "/", label: "Overview", icon: LayoutDashboard },
  { id: "inbox", href: "/inbox", label: "Inbox", icon: Inbox },
  { id: "cases", href: "/cases", label: "Customer cases", icon: Layers },
  {
    id: "reports",
    href: "/reports",
    label: "Kertas kerja",
    icon: FileCheck2,
    gloss: "Work paper report",
  },
  { id: "settings", href: "/settings", label: "Configuration", icon: Settings },
];
export function Shell({
  children,
  title,
  subtitle,
  action,
}: {
  children: React.ReactNode;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  const { user, loading, online, signOut, upload, notify } = usePlatform();
  const pathname = usePathname(),
    router = useRouter();
  const identity = pageIdentity(pathname),
    PageIcon = identity.icon;

  const { data: rolePermissions } = useData<RolePermissionsMap>("/access/role-permissions", 0);
  const { data: branches } = useData<Branch[]>("/branches", 0);

  const defaultRoleMenus: Record<string, string[]> = {
    bank_admin: ["overview", "inbox", "cases", "reports", "upload", "settings"],
    branch_admin: ["overview", "inbox", "cases", "reports", "upload", "settings"],
    officer: ["overview", "inbox", "cases", "upload"],
    reviewer: ["overview", "inbox", "cases", "reports"],
    auditor: ["overview", "cases", "reports"],
  };

  const userRole = user?.role || "officer";
  const roleAllowedMenus = rolePermissions?.[userRole]?.menus || defaultRoleMenus[userRole] || ["overview", "cases"];

  const userBranchObjects = (branches && user?.branches)
    ? branches.filter(b => user.branches.includes(b.id))
    : [];

  const branchAllowedMenus = (userRole === "bank_admin" || userBranchObjects.length === 0)
    ? ["overview", "inbox", "cases", "reports", "upload", "settings"]
    : Array.from(new Set(userBranchObjects.flatMap(b => b.menus || ["overview", "inbox", "cases", "reports", "upload", "settings"])));

  const effectiveMenus = userRole === "bank_admin"
    ? (rolePermissions?.bank_admin?.menus || defaultRoleMenus.bank_admin)
    : roleAllowedMenus.filter(m => branchAllowedMenus.includes(m));

  const visibleNav = nav.filter(item => effectiveMenus.includes(item.id));
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  if (loading) return <Busy label="Opening workspace…" />;
  if (!user) return <Busy label="Redirecting to sign in…" />;
  const leaveWorkspace = async () => {
    try {
      await signOut();
      router.replace("/login");
    } catch (e) {
      notify(
        e instanceof Error ? e.message : "Unable to sign out. Try again.",
        "error",
      );
    }
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">s.</span>
          <span>
            SQE<span className="brand-sub">DOCUMENT OPERATIONS</span>
          </span>
        </Link>
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {visibleNav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-label={n.label}
              title={n.label}
              aria-current={
                pathname === n.href ||
                (n.href !== "/" && pathname.startsWith(n.href))
                  ? "page"
                  : undefined
              }
              className={
                "nav-link " +
                (pathname === n.href ||
                (n.href !== "/" && pathname.startsWith(n.href))
                  ? "active"
                  : "")
              }
            >
              <n.icon size={19} />
              <span title={n.gloss}>{n.label}</span>
              {n.href === "/inbox" && <InboxCount />}
            </Link>
          ))}
        </nav>
        {effectiveMenus.includes("upload") && (
          <Link href="/upload" className="sidebar-upload">
            <Upload size={18} />
            Upload documents
            <ArrowUpRight size={16} />
          </Link>
        )}
        <div className="sidebar-foot">
          <div className="org-tag">
            <ShieldCheck size={17} />
            <span>{user.organization.toUpperCase()} organization</span>
            <span className="dev-dot" />
          </div>
          <div className="user-block">
            <div className="avatar">{user.name.slice(0, 1)}</div>
            <div>
              <strong>{user.name}</strong>
              <span>{user.role.replaceAll("_", " ")}</span>
            </div>
            <button
              title="Sign out"
              aria-label="Sign out"
              onClick={() => void leaveWorkspace()}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb">
            Workspace <span>/</span> {title}
          </span>
          <div className="topbar-right">
            <WorkspaceControls />
            <span
              className={
                "connection-state " + (online ? "connected" : "disconnected")
              }
              title="Browser network connection; job status is shown in each case"
            >
              <span />
              {online ? "Connected" : "Offline"}
            </span>
            <details className="account-menu">
              <summary aria-label="Account menu" title={user.name}>
                {user.name.slice(0, 1)}
              </summary>
              <div>
                <strong>{user.name}</strong>
                <small>{user.email}</small>
                <small>{user.role.replaceAll("_", " ")}</small>
                <button onClick={() => void leaveWorkspace()}>
                  <LogOut size={15} />
                  Sign out
                </button>
              </div>
            </details>
          </div>
        </header>
        {!online && (
          <div className="offline">
            <WifiOff size={16} />
            Connection interrupted. Accepted jobs continue in the background.
          </div>
        )}
        {upload && (
          <div className="upload-strip" role="status">
            <span>{upload.label}</span>
            <div className="strip-track">
              <span style={{ width: upload.progress + "%" }} />
            </div>
            <strong>{upload.progress}%</strong>
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          <div className={`page-head corporate-hero tone-${identity.tone}`}>
            <div className="page-heading-group">
              <span className="page-emblem">
                <PageIcon size={28} strokeWidth={1.6} aria-hidden />
              </span>
              <div className="page-heading-copy">
                <div className="eyebrow">{identity.label}</div>
                <h1>{title}</h1>
                <p>{subtitle}</p>
              </div>
            </div>
            {action && <div className="page-actions">{action}</div>}
            <PagePath path={pathname} />
          </div>
          {children}
        </main>
        <footer className="page-footer">
          <span>SQE · Document Automation</span>
          <span>Evidence-backed decisions. Traceable by design.</span>
        </footer>
      </div>
      <ToastNotifications />
    </div>
  );
}
function InboxCount() {
  const { data } = useData<Dashboard>("/dashboard", 8000);
  return data?.unread ? <span className="nav-count">{data.unread}</span> : null;
}
