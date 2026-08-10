export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-50">
      <section className="w-full max-w-3xl py-24">
        <p className="mb-5 text-sm font-semibold uppercase tracking-[0.24em] text-emerald-400">
          GafferTalk
        </p>
        <h1 className="max-w-2xl text-5xl font-semibold tracking-tight sm:text-7xl">
          Talk to your FPL team.
        </h1>
        <p className="mt-8 max-w-xl text-lg leading-8 text-slate-300">
          The application foundation is ready. Team loading and legal,
          data-driven recommendations are being built next.
        </p>
        <div className="mt-10 inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200">
          MVP development in progress
        </div>
      </section>
    </main>
  );
}
