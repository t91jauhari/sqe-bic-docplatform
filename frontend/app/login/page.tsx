"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ShieldCheck,
  Layers,
  CheckCircle2,
  Eye,
  EyeOff,
} from "lucide-react";
import { usePlatform } from "@/components/platform-provider";
import { Busy, ErrorNotice } from "@/components/ui";
export default function Login() {
  const { user, loading, signIn } = usePlatform(),
    router = useRouter();
  const [organization, setOrganization] = useState("sqe"),
    [email, setEmail] = useState("sqe@bic.local"),
    [password, setPassword] = useState(""),
    [visible, setVisible] = useState(false),
    [pending, setPending] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);
  if (loading) return <Busy label="Checking your session…" />;
  return (
    <div className="login-page">
      <section className="login-story">
        <div className="login-brand">
          <span className="brand-mark">s.</span>SQE
        </div>
        <span className="story-kicker">DOCUMENT AUTOMATION PLATFORM</span>
        <h1>
          Less paperwork.
          <br />
          More certainty.
        </h1>
        <p>
          One workspace to organize customer documents, validate every detail
          and prepare your kertas kerja.
        </p>
        <div className="story-features">
          <div>
            <Layers size={20} />
            <span>Customer cases, automatically organized</span>
          </div>
          <div>
            <CheckCircle2 size={20} />
            <span>SOP checks backed by document evidence</span>
          </div>
          <div>
            <ShieldCheck size={20} />
            <span>Branch-scoped access and a complete audit trail</span>
          </div>
        </div>
        <div className="story-foot">Built for banking operations.</div>
      </section>
      <section className="login-form-side">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setPending(true);
            setError("");
            try {
              await signIn(organization, email, password);
              router.replace("/");
            } catch (err) {
              setError(
                err instanceof Error ? err.message : "Unable to sign in.",
              );
            } finally {
              setPending(false);
            }
          }}
        >
          <span className="eyebrow">WELCOME TO YOUR WORKSPACE</span>
          <h2>Sign in to SQE</h2>
          <p>Use your organization account to continue.</p>
          {error && <ErrorNotice message={error} />}
          <label>
            Organization
            <input
              required
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              autoComplete="organization"
            />
          </label>
          <label>
            Email address
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <div className="password-input">
              <input
                required
                type={visible ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                aria-label={visible ? "Hide password" : "Show password"}
                onClick={() => setVisible(!visible)}
              >
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>
          <button className="primary login-submit" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
            <ArrowRight size={18} />
          </button>
          <div className="login-note">
            <span className="dev-dot" />
            Development environment
          </div>
        </form>
      </section>
    </div>
  );
}
