"use client";

import { useState } from "react";
import { ArrowRight, LogIn, UserPlus, Mail, Lock, User, Sparkles, ShieldCheck, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { login, signup } from "@/lib/api";
import type { User as UserType } from "@/types";

interface AuthGateProps {
  onAuthenticated: (user: UserType) => void;
}

function LogoMark({ className }: { className?: string }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
      <circle cx="5" cy="18" r="2.4" fill="currentColor" opacity="0.55" />
      <circle cx="12" cy="5" r="2.4" fill="currentColor" />
      <circle cx="19" cy="15" r="2.4" fill="currentColor" opacity="0.75" />
      <path d="M6.3 16.2L10.8 7.2M13.8 6.6l3.9 6.4M7.4 17.4l9.2-1.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" opacity="0.45" />
    </svg>
  );
}

export function AuthGate({ onAuthenticated }: AuthGateProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError("");
    if (!email.trim() || !password.trim() || (mode === "signup" && !name.trim())) {
      setError("Please fill in all fields");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    try {
      const response = mode === "signup" ? await signup(name.trim(), email.trim(), password) : await login(email.trim(), password);
      onAuthenticated(response.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") submit();
  };

  return (
    <main className="relative flex min-h-screen overflow-hidden bg-background text-foreground">
      {/* Atmosphere */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-grid bg-grid-fade" />
        <div className="glow-orb left-[-120px] top-[-120px] h-[480px] w-[640px] bg-accent/20 animate-float-slow" />
        <div className="glow-orb right-[-160px] top-[28%] h-[420px] w-[420px] bg-violet-500/14" />
        <div className="glow-orb bottom-[-180px] left-[32%] h-[360px] w-[560px] bg-sky-500/10" />
      </div>

      {/* Left — branding */}
      <section className="relative hidden flex-1 flex-col px-10 py-10 lg:flex lg:px-14 xl:px-16">
        <div className="mx-auto flex w-full max-w-[560px] flex-1 flex-col justify-between">
        <div>
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent shadow-[0_0_28px_-8px] shadow-accent/50">
              <LogoMark />
            </span>
            <span className="font-display text-lg font-semibold tracking-tight">RAGnostic</span>
            <span className="ml-2 rounded-full border border-border/60 bg-card/60 px-2.5 py-1 text-[11px] font-medium tracking-wide text-foreground/55">ADAPTIVE RAG</span>
          </div>
        </div>

        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/8 px-3 py-1.5 text-xs font-medium text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_10px_2px] shadow-accent/50" />
            Supabase · Chroma · NVIDIA NIM
          </p>
          <h1 className="mt-6 font-display text-[40px] font-bold leading-[1.02] tracking-tight xl:text-[48px]">
            Answers grounded in
            <br />
            <span className="text-gradient">your documents</span>
          </h1>
          <p className="mt-6 max-w-[480px] text-[15px] leading-7 text-foreground/60">
            A research-ready chatbot with adaptive threshold retrieval, knowledge-graph expansion, and structured streaming answers. Index PDFs, then watch it cite every claim.
          </p>

          <div className="mt-8 grid grid-cols-3 gap-3">
            {[
              { icon: Zap, label: "Streaming", sub: "SSE tokens" },
              { icon: ShieldCheck, label: "Cited", sub: "Every answer" },
              { icon: Sparkles, label: "Adaptive", sub: "Threshold policy" },
            ].map((f) => (
              <div key={f.label} className="rounded-2xl border border-border/40 bg-card/50 p-4 backdrop-blur">
                <f.icon className="h-4 w-4 text-accent" />
                <p className="mt-2 text-sm font-semibold">{f.label}</p>
                <p className="text-xs text-foreground/45">{f.sub}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-2 text-xs text-foreground/35">
            <span className="rounded-full border border-border/40 bg-card/40 px-3 py-1.5">Standard RAG</span>
            <span className="rounded-full border border-border/40 bg-card/40 px-3 py-1.5">Threshold-Gated</span>
            <span className="rounded-full border border-border/40 bg-card/40 px-3 py-1.5">Graph-RAG</span>
            <span className="rounded-full border border-border/40 bg-card/40 px-3 py-1.5">Chroma + PG</span>
          </div>
        </div>

        <p className="text-xs text-foreground/30">© {new Date().getFullYear()} RAGnostic · Adaptive retrieval-augmented generation</p>
        </div>
      </section>

      {/* Right — auth card */}
      <section className="relative flex w-full items-center justify-center px-4 py-10 lg:w-[480px] xl:w-[520px] lg:justify-end lg:pr-10 lg:border-l lg:border-border/40 lg:bg-card/20 lg:backdrop-blur-xl">
        {/* Mobile logo */}
        <div className="absolute top-6 left-6 flex items-center gap-2 lg:hidden">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
            <LogoMark />
          </span>
          <span className="font-display text-[15px] font-semibold">RAGnostic</span>
        </div>

        <div className="w-full max-w-[380px]">
          <div className="mb-8 hidden lg:block">
            <h2 className="font-display text-2xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create account"}</h2>
            <p className="mt-2 text-sm text-foreground/55">
              {mode === "login" ? "Sign in to continue to your workspace." : "Sign up to start indexing documents."}
            </p>
          </div>
          <div className="mb-6 lg:hidden">
            <h2 className="pt-12 text-2xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create account"}</h2>
            <p className="mt-1 text-sm text-foreground/55">{mode === "login" ? "Sign in to continue" : "Create your RAGnostic account"}</p>
          </div>

          {/* Toggle */}
          <div className="mb-6 flex rounded-xl bg-secondary/60 p-1 ring-1 ring-border/40">
            <button
              onClick={() => {
                setMode("login");
                setError("");
              }}
              className={`flex-1 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${mode === "login" ? "bg-card text-foreground shadow-sm ring-1 ring-border/50" : "text-foreground/50 hover:text-foreground/80"}`}
            >
              Login
            </button>
            <button
              onClick={() => {
                setMode("signup");
                setError("");
              }}
              className={`flex-1 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${mode === "signup" ? "bg-card text-foreground shadow-sm ring-1 ring-border/50" : "text-foreground/50 hover:text-foreground/80"}`}
            >
              Signup
            </button>
          </div>

          <div className="space-y-3.5">
            {mode === "signup" && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground/60">Name</label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/30" />
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onKeyDown={onKeyDown}
                    placeholder="Ada Lovelace"
                    autoComplete="name"
                    className="h-11 w-full rounded-xl border border-border/60 bg-card/60 py-2 pl-10 pr-3 text-sm text-foreground placeholder:text-foreground/30 outline-none backdrop-blur transition-all focus:border-accent/40 focus:ring-4 focus:ring-accent/10"
                  />
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground/60">Email</label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/30" />
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="you@company.com"
                  type="email"
                  autoComplete="email"
                  className="h-11 w-full rounded-xl border border-border/60 bg-card/60 py-2 pl-10 pr-3 text-sm text-foreground placeholder:text-foreground/30 outline-none backdrop-blur transition-all focus:border-accent/40 focus:ring-4 focus:ring-accent/10"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground/60">Password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/30" />
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="At least 8 characters"
                  type="password"
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  minLength={8}
                  className="h-11 w-full rounded-xl border border-border/60 bg-card/60 py-2 pl-10 pr-3 text-sm text-foreground placeholder:text-foreground/30 outline-none backdrop-blur transition-all focus:border-accent/40 focus:ring-4 focus:ring-accent/10"
                />
              </div>
              <p className="text-[11px] text-foreground/35">Must be at least 8 characters.</p>
            </div>

            {error && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2.5 text-sm leading-snug text-red-300">
                {error}
              </div>
            )}

            <Button
              onClick={submit}
              disabled={busy}
              className="h-11 w-full gap-2 rounded-xl bg-accent font-semibold text-accent-foreground shadow-[0_8px_24px_-12px] shadow-accent/60 hover:bg-accent/90 disabled:opacity-60"
            >
              {busy ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent-foreground/30 border-t-accent-foreground" />
                  Please wait
                </>
              ) : mode === "signup" ? (
                <>
                  <UserPlus className="h-4 w-4" />
                  Create account
                  <ArrowRight className="h-4 w-4" />
                </>
              ) : (
                <>
                  <LogIn className="h-4 w-4" />
                  Login
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>

            <p className="pt-1 text-center text-xs text-foreground/35">
              {mode === "login" ? "Don't have an account? " : "Already have an account? "}
              <button
                onClick={() => setMode(mode === "login" ? "signup" : "login")}
                className="font-medium text-accent hover:text-accent/80 underline-offset-4 hover:underline"
              >
                {mode === "login" ? "Sign up" : "Sign in"}
              </button>
            </p>
          </div>

          <p className="mt-8 text-center text-[11px] leading-relaxed text-foreground/25">
            By continuing you agree to our Terms and acknowledge our Privacy Policy.
          </p>
        </div>
      </section>
    </main>
  );
}
