export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      {/* Skeleton header matching AppTopNav height */}
      <div className="sticky top-0 z-40 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500/40 to-purple-600/40 animate-pulse" />
            <div className="space-y-1.5">
              <div className="h-5 w-32 rounded bg-secondary animate-pulse" />
              <div className="h-3 w-48 rounded bg-secondary animate-pulse" />
            </div>
          </div>
        </div>
      </div>

      {/* Skeleton content */}
      <div className="container mx-auto px-4 py-6 space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 rounded-xl border border-border bg-card p-4 animate-pulse">
              <div className="h-3 w-16 rounded bg-secondary mb-3" />
              <div className="h-6 w-24 rounded bg-secondary" />
            </div>
          ))}
        </div>
        <div className="h-64 rounded-xl border border-border bg-card animate-pulse" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="h-48 rounded-xl border border-border bg-card animate-pulse" />
          <div className="h-48 rounded-xl border border-border bg-card animate-pulse" />
        </div>
      </div>
    </div>
  );
}
