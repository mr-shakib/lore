import Sidebar from "@/components/sidebar";
import BootstrapOnMount from "@/components/bootstrap-on-mount";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface flex">
      <BootstrapOnMount />
      <Sidebar />
      <main className="ml-56 flex-1 min-h-screen">
        <div className="max-w-6xl mx-auto px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
