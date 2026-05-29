"use client";

import { useState } from "react";
import { ArrowRight, LogIn, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { login, signup } from "@/lib/api";
import type { User } from "@/types";

interface AuthGateProps {
  onAuthenticated: (user: User) => void;
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
    setBusy(true);
    try {
      const response =
        mode === "signup"
          ? await signup(name, email, password)
          : await login(email, password);
      onAuthenticated(response.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen bg-background text-foreground">
      <section className="flex flex-1 flex-col justify-center px-6 py-10 md:px-16">
        <div className="max-w-xl">
          <p className="text-sm font-medium text-foreground/50">
            Adaptive Retrieval-Augmented Generation
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-normal md:text-6xl">
            RAGnostic
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-foreground/60">
            A research-ready chatbot backend with semantic retrieval, graph
            expansion, contextual bandits, MongoDB memory, and Kimi K2.6
            streaming responses.
          </p>
          <div className="mt-8 flex items-center gap-3 text-sm text-foreground/45">
            <span>Standard RAG</span>
            <span>Graph-RAG</span>
            <span>Hybrid</span>
            <span>LinUCB</span>
          </div>
        </div>
      </section>

      <section className="flex w-full items-center justify-center border-l border-border/40 px-6 md:w-[420px]">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex rounded-lg bg-foreground/5 p-1">
            <button
              onClick={() => setMode("login")}
              className={`flex-1 rounded-md px-3 py-2 text-sm ${mode === "login" ? "bg-background text-foreground" : "text-foreground/50"}`}
            >
              Login
            </button>
            <button
              onClick={() => setMode("signup")}
              className={`flex-1 rounded-md px-3 py-2 text-sm ${mode === "signup" ? "bg-background text-foreground" : "text-foreground/50"}`}
            >
              Signup
            </button>
          </div>
          <div className="space-y-3">
            {mode === "signup" && (
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Name"
                className="h-11 w-full rounded-lg border border-border/60 bg-transparent px-3 text-sm outline-none focus:border-foreground/30"
              />
            )}
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Email"
              type="email"
              className="h-11 w-full rounded-lg border border-border/60 bg-transparent px-3 text-sm outline-none focus:border-foreground/30"
            />
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password (min 8 characters)"
              type="password"
              minLength={8}
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button
              onClick={submit}
              disabled={busy}
              className="h-11 w-full gap-2"
            >
              {mode === "signup" ? (
                <UserPlus className="h-4 w-4" />
              ) : (
                <LogIn className="h-4 w-4" />
              )}
              {busy
                ? "Please wait"
                : mode === "signup"
                  ? "Create account"
                  : "Login"}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
