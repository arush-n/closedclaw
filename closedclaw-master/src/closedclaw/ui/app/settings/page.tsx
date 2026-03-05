"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  Settings as SettingsIcon,
  Loader2,
  Eye,
  EyeOff,
  Copy,
  CheckCircle2,
  Shield,
  Cpu,
  Globe,
  Lock,
  Brain,
} from "lucide-react";

interface ConfigData {
  provider?: string;
  default_model?: string;
  openai_api_key?: string;
  anthropic_api_key?: string;
  groq_api_key?: string;
  together_api_key?: string;
  default_sensitivity?: number;
  require_consent_level?: number;
  enable_redaction?: boolean;
  enable_encryption?: boolean;
  local_engine?: {
    enabled?: boolean;
    hardware_profile?: string;
    llm_model?: string;
    ollama_base_url?: string;
  };
  host?: string;
  port?: number;
  auth_token?: string;
  [key: string]: unknown;
}

function SettingsSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="glass-card rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
      </div>
      <div className="grid gap-3">{children}</div>
    </div>
  );
}

function FieldRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-sm text-slate-400 shrink-0">{label}</label>
      <div className="flex-1 max-w-[280px]">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);

  // Editable fields
  const [provider, setProvider] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [sensitivity, setSensitivity] = useState(1);
  const [consentLevel, setConsentLevel] = useState(2);
  const [redaction, setRedaction] = useState(true);

  // OpenMemory config state
  const [omLlmProvider, setOmLlmProvider] = useState("ollama");
  const [omLlmModel, setOmLlmModel] = useState("");
  const [omLlmOllamaUrl, setOmLlmOllamaUrl] = useState("");
  const [omEmbedProvider, setOmEmbedProvider] = useState("ollama");
  const [omEmbedModel, setOmEmbedModel] = useState("");
  const [omEmbedOllamaUrl, setOmEmbedOllamaUrl] = useState("");
  const [omCustomInstructions, setOmCustomInstructions] = useState("");
  const [omLoading, setOmLoading] = useState(false);
  const [omSaving, setOmSaving] = useState(false);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/config", { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to load config");
      const data = await res.json();
      setConfig(data);
      setProvider(data.provider || "openai");
      setDefaultModel(data.default_model || "");
      setSensitivity(data.default_sensitivity ?? 1);
      setConsentLevel(data.require_consent_level ?? 2);
      setRedaction(data.enable_redaction ?? true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load config");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOpenMemoryConfig = useCallback(async () => {
    setOmLoading(true);
    try {
      const [llmRes, embedRes, instrRes] = await Promise.allSettled([
        fetch("/api/openmemory/config/mem0/llm", { cache: "no-store" }),
        fetch("/api/openmemory/config/mem0/embedder", { cache: "no-store" }),
        fetch("/api/openmemory/config/openmemory", { cache: "no-store" }),
      ]);
      if (llmRes.status === "fulfilled" && llmRes.value.ok) {
        const d = (await llmRes.value.json()) as any;
        setOmLlmProvider(d.provider || "ollama");
        setOmLlmModel(d.config?.model || "");
        setOmLlmOllamaUrl(d.config?.ollama_base_url || "");
      }
      if (embedRes.status === "fulfilled" && embedRes.value.ok) {
        const d = (await embedRes.value.json()) as any;
        setOmEmbedProvider(d.provider || "ollama");
        setOmEmbedModel(d.config?.model || "");
        setOmEmbedOllamaUrl(d.config?.ollama_base_url || "");
      }
      if (instrRes.status === "fulfilled" && instrRes.value.ok) {
        const d = (await instrRes.value.json()) as any;
        setOmCustomInstructions(d.custom_instructions || "");
      }
    } catch {
      // silently fail — openmemory may not be running
    } finally {
      setOmLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadOpenMemoryConfig();
  }, [loadConfig, loadOpenMemoryConfig]);

  useEffect(() => {
    if (!success) return;
    const t = setTimeout(() => setSuccess(null), 3000);
    return () => clearTimeout(t);
  }, [success]);

  const saveConfig = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          default_model: defaultModel,
          default_sensitivity: sensitivity,
          require_consent_level: consentLevel,
          enable_redaction: redaction,
        }),
      });
      if (!res.ok) throw new Error("Failed to save config");
      setSuccess("Settings saved successfully.");
      await loadConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveOpenMemoryConfig = async () => {
    setOmSaving(true);
    try {
      await Promise.all([
        fetch("/api/openmemory/config/mem0/llm", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: omLlmProvider,
            config: {
              model: omLlmModel,
              ollama_base_url: omLlmOllamaUrl,
            },
          }),
        }),
        fetch("/api/openmemory/config/mem0/embedder", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: omEmbedProvider,
            config: {
              model: omEmbedModel,
              ollama_base_url: omEmbedOllamaUrl,
            },
          }),
        }),
        fetch("/api/openmemory/config/openmemory", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            custom_instructions: omCustomInstructions,
          }),
        }),
      ]);
      setSuccess("OpenMemory settings saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save OpenMemory settings."
      );
    } finally {
      setOmSaving(false);
    }
  };

  const copyToken = async () => {
    try {
      const tokenPath = "~/.closedclaw/token";
      await navigator.clipboard.writeText(tokenPath);
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    } catch {
      /* noop */
    }
  };

  if (loading) {
    return (
      <div className="page-container animate-fadeIn flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
      </div>
    );
  }

  return (
    <div className="page-container animate-fadeIn">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
          <SettingsIcon className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h1 className="section-title">Settings</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Configure closedclaw server and privacy options
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4">
          <FeedbackBanner
            message={error}
            variant="error"
            onClose={() => setError(null)}
          />
        </div>
      )}
      {success && (
        <div className="mb-4">
          <FeedbackBanner
            message={success}
            variant="success"
            onClose={() => setSuccess(null)}
          />
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* General */}
        <SettingsSection
          title="General"
          icon={<Globe className="w-4 h-4 text-blue-400" />}
        >
          <FieldRow label="Provider">
            <select
              className="glass-input rounded-lg px-3 py-2 text-sm w-full"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="ollama">Ollama (Local)</option>
              <option value="groq">Groq</option>
              <option value="together">Together</option>
            </select>
          </FieldRow>
          <FieldRow label="Default Model">
            <input
              className="glass-input rounded-lg px-3 py-2 text-sm w-full"
              value={defaultModel}
              onChange={(e) => setDefaultModel(e.target.value)}
              placeholder="e.g. gpt-4o-mini"
            />
          </FieldRow>
          <FieldRow label="Server">
            <span className="text-sm text-slate-300">
              {config?.host || "127.0.0.1"}:{config?.port || 8765}
            </span>
          </FieldRow>
        </SettingsSection>

        {/* Privacy */}
        <SettingsSection
          title="Privacy"
          icon={<Shield className="w-4 h-4 text-emerald-400" />}
        >
          <FieldRow label="Default Sensitivity">
            <select
              className="glass-input rounded-lg px-3 py-2 text-sm w-full"
              value={sensitivity}
              onChange={(e) => setSensitivity(Number(e.target.value))}
            >
              <option value={0}>0 — Public</option>
              <option value={1}>1 — Normal</option>
              <option value={2}>2 — Sensitive</option>
              <option value={3}>3 — Highly Sensitive</option>
            </select>
          </FieldRow>
          <FieldRow label="Consent Required At">
            <select
              className="glass-input rounded-lg px-3 py-2 text-sm w-full"
              value={consentLevel}
              onChange={(e) => setConsentLevel(Number(e.target.value))}
            >
              <option value={0}>Level 0+</option>
              <option value={1}>Level 1+</option>
              <option value={2}>Level 2+ (default)</option>
              <option value={3}>Level 3 only</option>
            </select>
          </FieldRow>
          <FieldRow label="PII Redaction">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={redaction}
                onChange={(e) => setRedaction(e.target.checked)}
                className="rounded border-slate-600"
              />
              <span className="text-sm text-slate-300">
                {redaction ? "Enabled" : "Disabled"}
              </span>
            </label>
          </FieldRow>
          <FieldRow label="Encryption">
            <span className="text-sm text-emerald-400">Always On</span>
          </FieldRow>
        </SettingsSection>

        {/* Local Engine */}
        <SettingsSection
          title="Local Engine"
          icon={<Cpu className="w-4 h-4 text-orange-400" />}
        >
          <FieldRow label="Status">
            <span
              className={`text-sm ${
                config?.local_engine?.enabled
                  ? "text-emerald-400"
                  : "text-slate-500"
              }`}
            >
              {config?.local_engine?.enabled ? "Enabled" : "Disabled"}
            </span>
          </FieldRow>
          <FieldRow label="Hardware Profile">
            <span className="text-sm text-slate-300 capitalize">
              {config?.local_engine?.hardware_profile || "—"}
            </span>
          </FieldRow>
          <FieldRow label="LLM Model">
            <span className="text-sm text-slate-300">
              {config?.local_engine?.llm_model || "—"}
            </span>
          </FieldRow>
          <FieldRow label="Ollama URL">
            <span className="text-sm text-slate-300 truncate block">
              {config?.local_engine?.ollama_base_url || "—"}
            </span>
          </FieldRow>
        </SettingsSection>

        {/* Security */}
        <SettingsSection
          title="Security"
          icon={<Lock className="w-4 h-4 text-red-400" />}
        >
          <FieldRow label="API Keys">
            <button
              type="button"
              onClick={() => setShowKeys(!showKeys)}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              {showKeys ? (
                <EyeOff className="w-3.5 h-3.5" />
              ) : (
                <Eye className="w-3.5 h-3.5" />
              )}
              {showKeys ? "Hide" : "Show"} keys
            </button>
          </FieldRow>
          {(["openai_api_key", "anthropic_api_key", "groq_api_key", "together_api_key"] as const).map(
            (key) => {
              const val = config?.[key] as string | undefined;
              if (!val) return null;
              return (
                <FieldRow key={key} label={key.replace(/_api_key$/, "").replace(/_/g, " ")}>
                  <span className="text-sm text-slate-300 font-mono truncate block">
                    {showKeys ? val : "••••••••"}
                  </span>
                </FieldRow>
              );
            }
          )}
          <FieldRow label="Auth Token">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-mono">
                ~/.closedclaw/token
              </span>
              <button
                type="button"
                onClick={copyToken}
                className="p-1 hover:bg-white/[0.06] rounded transition-colors"
                title="Copy token path"
              >
                {copiedToken ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5 text-slate-500" />
                )}
              </button>
            </div>
          </FieldRow>
        </SettingsSection>
      </div>

      {/* OpenMemory Configuration */}
      <div className="mt-6">
        <SettingsSection
          title="OpenMemory (Openclaw MCP)"
          icon={<Brain className="w-4 h-4 text-violet-400" />}
        >
          {omLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading OpenMemory config...
            </div>
          ) : (
            <>
              {/* LLM sub-section */}
              <div className="text-xs text-slate-500 uppercase tracking-wide pt-1">
                LLM
              </div>
              <FieldRow label="Provider">
                <select
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omLlmProvider}
                  onChange={(e) => setOmLlmProvider(e.target.value)}
                >
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </FieldRow>
              <FieldRow label="Model">
                <input
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omLlmModel}
                  onChange={(e) => setOmLlmModel(e.target.value)}
                  placeholder="e.g. llama3.2:3b"
                />
              </FieldRow>
              <FieldRow label="Ollama URL">
                <input
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omLlmOllamaUrl}
                  onChange={(e) => setOmLlmOllamaUrl(e.target.value)}
                  placeholder="http://ollama:11434"
                />
              </FieldRow>

              {/* Embedder sub-section */}
              <div className="text-xs text-slate-500 uppercase tracking-wide pt-4 border-t border-white/[0.05]">
                Embedder
              </div>
              <FieldRow label="Provider">
                <select
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omEmbedProvider}
                  onChange={(e) => setOmEmbedProvider(e.target.value)}
                >
                  <option value="ollama">Ollama</option>
                  <option value="openai">OpenAI</option>
                </select>
              </FieldRow>
              <FieldRow label="Model">
                <input
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omEmbedModel}
                  onChange={(e) => setOmEmbedModel(e.target.value)}
                  placeholder="e.g. nomic-embed-text"
                />
              </FieldRow>
              <FieldRow label="Ollama URL">
                <input
                  className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                  value={omEmbedOllamaUrl}
                  onChange={(e) => setOmEmbedOllamaUrl(e.target.value)}
                  placeholder="http://ollama:11434"
                />
              </FieldRow>

              {/* Custom Instructions */}
              <div className="text-xs text-slate-500 uppercase tracking-wide pt-4 border-t border-white/[0.05]">
                Custom Instructions
              </div>
              <textarea
                className="glass-input rounded-lg px-3 py-2 text-sm w-full resize-none h-24"
                value={omCustomInstructions}
                onChange={(e) => setOmCustomInstructions(e.target.value)}
                placeholder="System-level instructions for memory extraction..."
              />
              <div>
                <Button
                  onClick={saveOpenMemoryConfig}
                  disabled={omSaving}
                >
                  {omSaving && (
                    <Loader2 className="w-4 h-4 animate-spin mr-1" />
                  )}
                  Save OpenMemory Settings
                </Button>
              </div>
            </>
          )}
        </SettingsSection>
      </div>

      {/* Save */}
      <div className="mt-6 flex items-center gap-3">
        <Button onClick={saveConfig} disabled={saving}>
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          Save Settings
        </Button>
        <Button variant="outline" onClick={loadConfig} disabled={loading}>
          Reset
        </Button>
      </div>
    </div>
  );
}
