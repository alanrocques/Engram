import {
  Outlet,
  createRootRouteWithContext,
  useRouterState,
  Link,
} from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  BookOpen,
  Activity,
  Flag,
  AlertTriangle,
  Settings,
  ChevronLeft,
  ChevronRight,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
});

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/lessons", label: "Lessons", icon: BookOpen },
  { to: "/traces", label: "Traces", icon: Activity },
  { to: "/flagged", label: "Flagged", icon: Flag },
  { to: "/failure-queue", label: "Failure Queue", icon: AlertTriangle },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUiStore();
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  return (
    <aside
      className={cn(
        "relative flex h-screen flex-col border-r border-sidebar-border bg-sidebar transition-all duration-200",
        sidebarCollapsed ? "w-12" : "w-60",
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center border-b border-sidebar-border px-3">
        <div
          className={cn(
            "flex items-center gap-2.5 overflow-hidden",
            sidebarCollapsed && "justify-center",
          )}
        >
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-white/10">
            <Brain className="h-4 w-4 text-white" />
          </div>
          {!sidebarCollapsed && (
            <span className="truncate text-sm font-semibold text-sidebar-foreground">
              Mnemosyne
            </span>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
          const isActive =
            to === "/"
              ? currentPath === "/"
              : currentPath.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                sidebarCollapsed && "justify-center px-0",
              )}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {!sidebarCollapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-16 flex h-6 w-6 items-center justify-center rounded-full border border-sidebar-border bg-sidebar text-muted-foreground hover:text-foreground"
        aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {sidebarCollapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  );
}

function Header() {
  const routerState = useRouterState();
  const path = routerState.location.pathname;

  const crumbs: string[] = ["Mnemosyne"];
  const segments = path.split("/").filter(Boolean);
  segments.forEach((seg) => {
    crumbs.push(seg.charAt(0).toUpperCase() + seg.slice(1).replace(/-/g, " "));
  });

  return (
    <header className="flex h-14 items-center border-b border-border px-6">
      <nav aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5 text-sm">
          {crumbs.map((crumb, i) => (
            <li key={i} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-muted-foreground">/</span>}
              <span
                className={cn(
                  i === crumbs.length - 1
                    ? "font-medium text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {crumb}
              </span>
            </li>
          ))}
        </ol>
      </nav>
    </header>
  );
}

function RootLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] px-6 py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
