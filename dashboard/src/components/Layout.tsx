import React from "react";

type NavSection =
  | "overview"
  | "findings"
  | "hotspots"
  | "silos"
  | "risks"
  | "roadmap";

interface LayoutProps {
  activeSection: NavSection;
  onNavigate: (section: NavSection) => void;
  children: React.ReactNode;
}

const NAV_ITEMS: { id: NavSection; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "O" },
  { id: "findings", label: "Findings", icon: "F" },
  { id: "hotspots", label: "Hotspots", icon: "H" },
  { id: "silos", label: "Knowledge Silos", icon: "S" },
  { id: "risks", label: "Risk Prediction", icon: "R" },
  { id: "roadmap", label: "Roadmap", icon: "M" },
];

export function Layout({
  activeSection,
  onNavigate,
  children,
}: LayoutProps): React.ReactElement {
  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 text-white flex flex-col shadow-lg">
        <div className="px-4 py-5 border-b border-gray-700">
          <h1 className="text-xl font-bold text-white tracking-tight">
            cppulse
          </h1>
          <p className="text-xs text-gray-400 mt-1">C++ Health Analyzer</p>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                activeSection === item.id
                  ? "bg-blue-600 text-white"
                  : "text-gray-300 hover:bg-gray-700 hover:text-white"
              }`}
            >
              <span className="w-5 h-5 flex items-center justify-center text-xs font-bold bg-gray-600 rounded">
                {item.icon}
              </span>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-gray-700">
          <p className="text-xs text-gray-500">cppulse v0.1.0</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
