"use client";

import { useState } from "react";
import { ArrowRight, LogIn, UserPlus, Mail, Lock, User, ShieldCheck, Zap, FileText } from "lucide-react";
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
    <main className="flex min-h-dvh bg-background text-foreground">
      {/* Left — branding */}
      <section className="relative hidden flex-1 flex-col px-10 py-8 lg:flex lg:px-14">
        <div className="mx-auto flex w-full max-w-[520px] flex-1 flex-col">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-foreground">
              <LogoMark />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">RAGnostic</span>
            <span className="mono-meta ml-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px] text-foreground/55">ADAPTIVE RAG</span>
          </div>

          <div className="flex flex-1 flex-col justify-center py-12">
            <p className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground/60">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Supabase · Chroma · NVIDIA NIM
            </p>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.08] tracking-tight xl:text-[44px]">
              Answers grounded in your documents
            </h1>
            <p className="mt-4 max-w-[460px] text-[15px] leading-7 text-foreground/60">
              A research-ready chatbot with adaptive threshold retrieval, knowledge-graph expansion, and structured streaming answers. Index PDFs, then watch it cite every claim.
            </p>

            <div className="mt-8 grid grid-cols-3 gap-3">
              {[
                { icon: Zap, label: "Streaming", sub: "SSE tokens" },
                { icon: ShieldCheck, label: "Cited", sub: "Every answer" },
                { icon: FileText, label: "Adaptive", sub: "Threshold policy" },
              ].map((f) => (
                <div key={f.label} className="rounded-xl border border-border bg-card p-4">
                  <f.icon className="h-4 w-4 text-foreground/70" />
                  <p className="mt-2 text-sm font-medium">{f.label}</p>
                  <p className="text-xs text-foreground/50">{f.sub}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="text-xs text-foreground/40">© {new Date().getFullYear()} RAGnostic · Adaptive retrieval-augmented generation</p>
        </div>
      </section>

      {/* Right — auth card */}
      <section className="flex w-full flex-col border-border lg:w-[560px] lg:border-l lg:bg-card/40 xl:w-[600px]">
        <div className="flex items-center gap-2 px-4 pt-5 lg:hidden">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-foreground">
            <LogoMark />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">RAGnostic</span>
        </div>

        <div className="flex flex-1 items-center justify-center px-4 py-10 lg:justify-start lg:pl-14 xl:pl-16">
          <div className="w-full max-w-[360px] lg:mr-auto">
            <div className="mb-6">
              <h2 className="text-2xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create account"}</h2>
              <p className="mt-1.5 text-sm text-foreground/60">
                {mode === "login" ? "Sign in to continue to your workspace." : "Sign up to start indexing documents."}
              </p>
            </div>

            {/* Toggle */}
            <div className="mb-5 flex rounded-lg border border-border bg-secondary/60 p-1">
              <button
                onClick={() => {
                  setMode("login");
                  setError("");
                }}
                className={`h-9 flex-1 rounded-md px-3 text-sm font-medium transition-colors ${mode === "login" ? "bg-card text-foreground shadow-subtle ring-1 ring-border" : "text-foreground/55 hover:text-foreground"}`}
              >
                Login
              </button>
              <button
                onClick={() => {
                  setMode("signup");
                  setError("");
                }}
                className={`h-9 flex-1 rounded-md px-3 text-sm font-medium transition-colors ${mode === "signup" ? "bg-card text-foreground shadow-subtle ring-1 ring-border" : "text-foreground/55 hover:text-foreground"}`}
              >
                Signup
              </button>
            </div>

            <div className="space-y-3.5">
              {mode === "signup" && (
                <div className="space-y-1.5">
                  <label className="text-[13px] font-medium text-foreground/70">Name</label>
                  <div className="relative">
                    <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/35" />
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={onKeyDown}
                      placeholder="Ada Lovelace"
                      autoComplete="name"
                      className="h-11 w-full rounded-lg border border-border bg-background py-2 pl-10 pr-3 text-[16px] text-foreground outline-none transition-colors placeholder:text-foreground/35 focus:border-foreground/25 focus:ring-2 focus:ring-foreground/10 sm:text-sm"
                    />
                  </div>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-foreground/70">Email</label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/35" />
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={onKeyDown}
                    placeholder="you@company.com"
                    type="email"
                    autoComplete="email"
                    className="h-11 w-full rounded-lg border border-border bg-background py-2 pl-10 pr-3 text-[16px] text-foreground outline-none transition-colors placeholder:text-foreground/35 focus:border-foreground/25 focus:ring-2 focus:ring-foreground/10 sm:text-sm"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-foreground/70">Password</label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-foreground/35" />
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={onKeyDown}
                    placeholder="At least 8 characters"
                    type="password"
                    autoComplete={mode === "signup" ? "new-password" : "current-password"}
                    minLength={8}
                    className="h-11 w-full rounded-lg border border-border bg-background py-2 pl-10 pr-3 text-[16px] text-foreground outline-none transition-colors placeholder:text-foreground/35 focus:border-foreground/25 focus:ring-2 focus:ring-foreground/10 sm:text-sm"
                  />
                </div>
              </div>

              {error && (
                <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2.5 text-sm leading-snug text-red-300" role="alert">
                  {error}
                </div>
              )}

              <Button
                onClick={submit}
                disabled={busy}
                className="h-11 w-full gap-2 rounded-lg disabled:opacity-60"
              >
                {busy ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
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

              <p className="pt-1 text-center text-[13px] text-foreground/50">
                {mode === "login" ? "Don't have an account? " : "Already have an account? "}
                <button
                  onClick={() => setMode(mode === "login" ? "signup" : "login")}
                  className="font-medium text-foreground underline-offset-4 hover:underline"
                >
                  {mode === "login" ? "Sign up" : "Sign in"}
                </button>
              </p>
            </div>

            <p className="mt-8 text-center text-[11px] leading-relaxed text-foreground/35">
              By continuing you agree to our Terms and acknowledge our Privacy Policy.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
