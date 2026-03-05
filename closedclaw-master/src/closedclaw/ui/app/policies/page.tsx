"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import { Shield, Search, Copy, CheckCircle2, FlaskConical, Loader2, ToggleLeft, ToggleRight, Pencil, Trash2, CopyPlus, ChevronDown, ChevronUp, Info } from "lucide-react";

type PolicyAction = "PERMIT" | "REDACT" | "BLOCK" | "CONSENT_REQUIRED";

interface PolicyRule {
  id: string;
  name: string;
  description?: string;
  priority: number;
  enabled: boolean;
  action: PolicyAction;
  conditions: {
    sensitivity_min?: number;
    sensitivity_max?: number;
    tags_include?: string[];
    provider_is?: string[];
    provider_not?: string[];
  };
  redact_entities?: string[];
}

interface PolicyFormState {
  id: string;
  name: string;
  description: string;
  priority: number;
  action: PolicyAction;
  enabled: boolean;
  sensitivityMin: string;
  sensitivityMax: string;
  tagsInclude: string;
  providerIs: string;
  providerNot: string;
  redactEntities: string;
}

const EMPTY_FORM: PolicyFormState = {
  id: "",
  name: "",
  description: "",
  priority: 50,
  action: "REDACT",
  enabled: true,
  sensitivityMin: "",
  sensitivityMax: "",
  tagsInclude: "",
  providerIs: "",
  providerNot: "",
  redactEntities: "PERSON,EMAIL_ADDRESS,PHONE_NUMBER",
};

function parseCsv(input: string): string[] | undefined {
  const parsed = input
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return parsed.length > 0 ? parsed : undefined;
}

export default function PoliciesPage() {
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [form, setForm] = useState<PolicyFormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [copiedRuleId, setCopiedRuleId] = useState<string | null>(null);
  const [testOutput, setTestOutput] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [actionFilter, setActionFilter] = useState<"ALL" | PolicyAction>("ALL");
  const [enabledFilter, setEnabledFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [sortBy, setSortBy] = useState<"priority_desc" | "priority_asc" | "name_asc" | "name_desc">("priority_desc");
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const loadPolicies = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await fetch("/api/policies", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || data?.message || "Failed to load policies");
      }
      setRules(Array.isArray(data.rules) ? data.rules : []);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load policies");
      setRules([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPolicies();
  }, [loadPolicies]);

  const updateField = <K extends keyof PolicyFormState>(key: K, value: PolicyFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const formPayload = useMemo(() => {
    return {
      id: form.id || undefined,
      name: form.name,
      description: form.description || undefined,
      priority: Number(form.priority),
      enabled: form.enabled,
      action: form.action,
      conditions: {
        sensitivity_min: form.sensitivityMin ? Number(form.sensitivityMin) : undefined,
        sensitivity_max: form.sensitivityMax ? Number(form.sensitivityMax) : undefined,
        tags_include: parseCsv(form.tagsInclude),
        provider_is: parseCsv(form.providerIs),
        provider_not: parseCsv(form.providerNot),
      },
      redact_entities: form.action === "REDACT" ? parseCsv(form.redactEntities) : undefined,
    };
  }, [form]);

  const savePolicy = async () => {
    if (!form.name.trim()) {
      setError("Policy name is required.");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const isUpdate = !!form.id;
      const response = await fetch(isUpdate ? `/api/policies/${form.id}` : "/api/policies", {
        method: isUpdate ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formPayload),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data?.detail || data?.message || "Unable to save policy");
      }

      setForm(EMPTY_FORM);
      setSuccess(isUpdate ? "Policy updated." : "Policy created.");
      await loadPolicies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save policy");
    } finally {
      setSaving(false);
    }
  };

  const deletePolicy = async (id: string) => {
    setError(null);
    setSuccess(null);
    const response = await fetch(`/api/policies/${id}`, { method: "DELETE" });
    if (!response.ok) {
      const data = await response.json();
      setError(data?.detail || data?.message || "Failed to delete policy");
      return;
    }
    setSuccess("Policy deleted.");
    await loadPolicies();
  };

  const toggleEnabled = async (rule: PolicyRule) => {
    setError(null);
    setSuccess(null);
    const response = await fetch(`/api/policies/${rule.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !rule.enabled }),
    });

    if (!response.ok) {
      const data = await response.json();
      setError(data?.detail || data?.message || "Failed to update policy state");
      return;
    }

    setSuccess(`Policy ${!rule.enabled ? "enabled" : "disabled"}.`);
    await loadPolicies();
  };

  const editRule = (rule: PolicyRule) => {
    setForm({
      id: rule.id,
      name: rule.name,
      description: rule.description || "",
      priority: rule.priority,
      enabled: rule.enabled,
      action: rule.action,
      sensitivityMin: rule.conditions.sensitivity_min?.toString() || "",
      sensitivityMax: rule.conditions.sensitivity_max?.toString() || "",
      tagsInclude: (rule.conditions.tags_include || []).join(", "),
      providerIs: (rule.conditions.provider_is || []).join(", "),
      providerNot: (rule.conditions.provider_not || []).join(", "),
      redactEntities: (rule.redact_entities || []).join(", "),
    });
  };

  const applyProfile = (profile: "HIPAA" | "GDPR" | "COPPA") => {
    if (profile === "HIPAA") {
      setForm({
        ...EMPTY_FORM,
        name: "HIPAA - Block PHI to cloud",
        action: "BLOCK",
        priority: 950,
        tagsInclude: "health,medical,phi",
        providerNot: "ollama",
      });
      return;
    }

    if (profile === "GDPR") {
      setForm({
        ...EMPTY_FORM,
        name: "GDPR - Consent for sensitive",
        action: "CONSENT_REQUIRED",
        priority: 920,
        sensitivityMin: "2",
      });
      return;
    }

    setForm({
      ...EMPTY_FORM,
      name: "COPPA - Block child data",
      action: "BLOCK",
      priority: 930,
      tagsInclude: "child,minors,coppa",
      providerNot: "ollama",
    });
  };

  const runPolicyTest = async () => {
    setTestLoading(true);
    const payload = {
      memory_text: "Patient diagnosis and medication details",
      sensitivity: 3,
      tags: ["health", "medical"],
      provider: "openai",
      source: "conversation",
    };

    try {
      const response = await fetch("/api/policies/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || "Policy test failed");
      }
      setTestOutput(`Action: ${data.action}${data.matched_rule ? ` • Rule: ${data.matched_rule.id}` : ""}`);
    } catch (err) {
      setTestOutput(err instanceof Error ? err.message : "Policy test failed");
    } finally {
      setTestLoading(false);
    }
  };

  const copyRuleId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedRuleId(id);
      setSuccess("Policy ID copied");
      window.setTimeout(() => setCopiedRuleId((current) => (current === id ? null : current)), 1200);
    } catch {
      setError("Unable to copy policy id");
    }
  };

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => setSuccess(null), 2400);
    return () => window.clearTimeout(timer);
  }, [success]);

  const filteredRules = useMemo(() => {
    const query = deferredSearchQuery.toLowerCase().trim();
    const base = rules.filter((rule) => {
      if (actionFilter !== "ALL" && rule.action !== actionFilter) return false;
      if (enabledFilter === "enabled" && !rule.enabled) return false;
      if (enabledFilter === "disabled" && rule.enabled) return false;
      if (!query) return true;

      return (
        rule.id.toLowerCase().includes(query) ||
        rule.name.toLowerCase().includes(query) ||
        (rule.description || "").toLowerCase().includes(query)
      );
    });

    if (sortBy === "priority_asc") {
      return [...base].sort((a, b) => a.priority - b.priority);
    }
    if (sortBy === "name_asc") {
      return [...base].sort((a, b) => a.name.localeCompare(b.name));
    }
    if (sortBy === "name_desc") {
      return [...base].sort((a, b) => b.name.localeCompare(a.name));
    }
    return [...base].sort((a, b) => b.priority - a.priority);
  }, [rules, deferredSearchQuery, actionFilter, enabledFilter, sortBy]);

  const summary = useMemo(
    () => ({
      total: rules.length,
      enabled: rules.filter((rule) => rule.enabled).length,
      disabled: rules.filter((rule) => !rule.enabled).length,
    }),
    [rules]
  );

  const [showAdvanced, setShowAdvanced] = useState(false);

  const ACTION_BADGE: Record<PolicyAction, string> = {
    PERMIT: "badge badge-success",
    REDACT: "badge badge-warning",
    BLOCK: "badge badge-danger",
    CONSENT_REQUIRED: "badge badge-primary",
  };

  const ACTION_LABELS: Record<PolicyAction, { label: string; description: string }> = {
    PERMIT: { label: "Allow", description: "Allow access to memories" },
    REDACT: { label: "Redact", description: "Allow with PII removed" },
    BLOCK: { label: "Block", description: "Deny access entirely" },
    CONSENT_REQUIRED: { label: "Ask First", description: "Require user consent" },
  };

  const PROFILE_DESCRIPTIONS: Record<string, string> = {
    HIPAA: "Blocks health/medical data from cloud providers",
    GDPR: "Requires consent for sensitive data (level 2+)",
    COPPA: "Blocks child-related data from cloud providers",
  };

  const policySummary = useMemo(() => {
    if (!form.name) return null;
    const actionLabel = ACTION_LABELS[form.action];
    const parts: string[] = [`This policy will ${actionLabel.label.toUpperCase()} memories`];
    const conditions: string[] = [];
    if (form.tagsInclude) conditions.push(`tagged "${form.tagsInclude}"`);
    if (form.sensitivityMin) conditions.push(`with sensitivity >= ${form.sensitivityMin}`);
    if (form.sensitivityMax) conditions.push(`with sensitivity <= ${form.sensitivityMax}`);
    if (form.providerIs) conditions.push(`sent to ${form.providerIs}`);
    if (form.providerNot) conditions.push(`not sent via ${form.providerNot}`);
    if (conditions.length > 0) parts.push(conditions.join(" and "));
    if (form.action === "REDACT" && form.redactEntities) parts.push(`(removing: ${form.redactEntities})`);
    return parts.join(" ");
  }, [form]);

  return (
    <div className="page-container animate-fadeIn">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
          <Shield className="w-5 h-5 text-violet-400" />
        </div>
        <div>
          <h1 className="section-title">Policy Manager</h1>
          <p className="text-xs text-slate-500 mt-0.5">{summary.total} policies configured</p>
        </div>
      </div>

      <div className="grid xl:grid-cols-[1.2fr_1fr] gap-6">
        {/* Policy List */}
        <section className="glass-card rounded-xl overflow-hidden">
          {/* Stats bar */}
          <div className="p-4 border-b border-white/[0.06] flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs">
              <span className="glass-stat rounded-lg px-3 py-1.5">
                Total <span className="text-slate-200 font-semibold ml-1.5">{summary.total}</span>
              </span>
              <span className="glass-stat rounded-lg px-3 py-1.5">
                Enabled <span className="text-emerald-400 font-semibold ml-1.5">{summary.enabled}</span>
              </span>
              <span className="glass-stat rounded-lg px-3 py-1.5">
                Disabled <span className="text-slate-400 font-semibold ml-1.5">{summary.disabled}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              {lastUpdated && <span className="text-[10px] text-slate-500">{lastUpdated.toLocaleTimeString()}</span>}
              <Button variant="outline" size="sm" onClick={loadPolicies} disabled={loading || saving}>
                Refresh
              </Button>
            </div>
          </div>

          {/* Filters */}
          <div className="p-4 border-b border-white/[0.06] flex flex-wrap gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                className="glass-input rounded-lg pl-10 pr-4 py-2 text-sm w-full"
                placeholder="Search policies..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <select
              aria-label="Filter policy action"
              className="glass-input rounded-lg px-3 py-2 text-sm"
              value={actionFilter}
              onChange={(event) => setActionFilter(event.target.value as "ALL" | PolicyAction)}
            >
              <option value="ALL">All actions</option>
              <option value="PERMIT">Allow (Permit)</option>
              <option value="REDACT">Redact (PII removed)</option>
              <option value="BLOCK">Block (Deny)</option>
              <option value="CONSENT_REQUIRED">Ask First (Consent)</option>
            </select>
            <select
              aria-label="Filter policy enabled state"
              className="glass-input rounded-lg px-3 py-2 text-sm"
              value={enabledFilter}
              onChange={(event) => setEnabledFilter(event.target.value as "all" | "enabled" | "disabled")}
            >
              <option value="all">All states</option>
              <option value="enabled">Enabled</option>
              <option value="disabled">Disabled</option>
            </select>
            <select
              aria-label="Sort policies"
              className="glass-input rounded-lg px-3 py-2 text-sm"
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as "priority_desc" | "priority_asc" | "name_asc" | "name_desc")}
            >
              <option value="priority_desc">Priority high-low</option>
              <option value="priority_asc">Priority low-high</option>
              <option value="name_asc">Name A-Z</option>
              <option value="name_desc">Name Z-A</option>
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSearchQuery("");
                setActionFilter("ALL");
                setEnabledFilter("all");
                setSortBy("priority_desc");
              }}
            >
              Reset
            </Button>
          </div>

          {/* Rules list */}
          <div className="max-h-[72vh] overflow-auto">
            {loading && (
              <div className="flex items-center gap-3 p-6 justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-violet-400" />
                <span className="text-slate-500 text-sm">Loading policies...</span>
              </div>
            )}
            {!loading && filteredRules.map((rule) => (
              <div key={rule.id} className="group p-4 border-b border-white/[0.05] hover:bg-white/[0.02] transition-colors">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm text-slate-200">{rule.name}</span>
                      {!rule.enabled && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-500">disabled</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] text-slate-500 font-mono truncate max-w-[180px]">{rule.id}</span>
                      <button
                        type="button"
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                        onClick={() => copyRuleId(rule.id)}
                        title="Copy ID"
                      >
                        {copiedRuleId === rule.id ? (
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-slate-500 hover:text-slate-300" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={ACTION_BADGE[rule.action]}>{ACTION_LABELS[rule.action].label}</span>
                    <span className="badge badge-neutral">P{rule.priority}</span>
                  </div>
                </div>
                <p className="text-xs text-slate-500 mt-2 line-clamp-2">{rule.description || "No description"}</p>
                <div className="mt-3 flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                  <Button size="sm" variant="outline" onClick={() => editRule(rule)}>
                    <Pencil className="w-3 h-3" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setForm({
                        id: "",
                        name: `${rule.name} Copy`,
                        description: rule.description || "",
                        priority: rule.priority,
                        enabled: rule.enabled,
                        action: rule.action,
                        sensitivityMin: rule.conditions.sensitivity_min?.toString() || "",
                        sensitivityMax: rule.conditions.sensitivity_max?.toString() || "",
                        tagsInclude: (rule.conditions.tags_include || []).join(", "),
                        providerIs: (rule.conditions.provider_is || []).join(", "),
                        providerNot: (rule.conditions.provider_not || []).join(", "),
                        redactEntities: (rule.redact_entities || []).join(", "),
                      })
                    }
                  >
                    <CopyPlus className="w-3 h-3" />
                    Dup
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => toggleEnabled(rule)}>
                    {rule.enabled ? <ToggleRight className="w-3 h-3" /> : <ToggleLeft className="w-3 h-3" />}
                    {rule.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => deletePolicy(rule.id)}>
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
            {!loading && filteredRules.length === 0 && (
              <div className="p-8 text-center">
                <Shield className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                <p className="text-sm text-slate-500">
                  {rules.length === 0
                    ? "No policies found. Create one using the editor."
                    : "No policies match current filters."}
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Policy Editor */}
        <section className="glass-card rounded-xl p-5 space-y-4 h-fit sticky top-4">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
            <h2 className="text-sm font-semibold text-slate-200">
              {form.id ? "Edit Policy" : "New Policy"}
            </h2>
          </div>

          {/* Compliance Quick-Start Profiles */}
          <div className="p-3 rounded-lg bg-violet-500/5 border border-violet-500/15">
            <h3 className="text-xs font-semibold text-violet-300 mb-2">Quick Start — Compliance Profiles</h3>
            <div className="grid gap-2">
              {(["HIPAA", "GDPR", "COPPA"] as const).map((profile) => (
                <button
                  key={profile}
                  type="button"
                  onClick={() => applyProfile(profile)}
                  className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/[0.04] transition-colors text-left group"
                >
                  <Shield className="w-4 h-4 text-violet-400 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-slate-200">{profile}</span>
                    <p className="text-[11px] text-slate-500">{PROFILE_DESCRIPTIONS[profile]}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <label className="text-sm text-slate-400 inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => updateField("enabled", event.target.checked)}
              className="rounded border-slate-600"
            />
            Rule enabled
          </label>

          <div className="grid gap-3">
            <input
              className="glass-input rounded-lg px-3 py-2.5 text-sm"
              placeholder="Policy name"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
            />
            <input
              className="glass-input rounded-lg px-3 py-2.5 text-sm"
              placeholder="Description"
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
            />
            <div className="grid grid-cols-2 gap-3">
              <select
                aria-label="Select policy action"
                className="glass-input rounded-lg px-3 py-2.5 text-sm"
                value={form.action}
                onChange={(e) => updateField("action", e.target.value as PolicyAction)}
              >
                {(Object.keys(ACTION_LABELS) as PolicyAction[]).map((key) => (
                  <option key={key} value={key}>
                    {ACTION_LABELS[key].label} — {ACTION_LABELS[key].description}
                  </option>
                ))}
              </select>
              <input
                className="glass-input rounded-lg px-3 py-2.5 text-sm"
                type="number"
                value={form.priority}
                onChange={(e) => updateField("priority", Number(e.target.value))}
                placeholder="Priority (0-1000)"
              />
            </div>

            {/* Advanced Conditions — collapsible */}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-300 transition-colors py-1"
            >
              {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              Advanced Conditions
              {(form.sensitivityMin || form.sensitivityMax || form.tagsInclude || form.providerIs || form.providerNot) && (
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              )}
            </button>
            {showAdvanced && (
              <div className="grid gap-3 pl-2 border-l-2 border-white/[0.06]">
                <div className="grid grid-cols-2 gap-3">
                  <input
                    className="glass-input rounded-lg px-3 py-2.5 text-sm"
                    placeholder="Sensitivity min (0-5)"
                    value={form.sensitivityMin}
                    onChange={(e) => updateField("sensitivityMin", e.target.value)}
                  />
                  <input
                    className="glass-input rounded-lg px-3 py-2.5 text-sm"
                    placeholder="Sensitivity max (0-5)"
                    value={form.sensitivityMax}
                    onChange={(e) => updateField("sensitivityMax", e.target.value)}
                  />
                </div>
                <input
                  className="glass-input rounded-lg px-3 py-2.5 text-sm"
                  placeholder="Tags include (e.g. health, medical)"
                  value={form.tagsInclude}
                  onChange={(e) => updateField("tagsInclude", e.target.value)}
                />
                <input
                  className="glass-input rounded-lg px-3 py-2.5 text-sm"
                  placeholder="Only for providers (e.g. openai, anthropic)"
                  value={form.providerIs}
                  onChange={(e) => updateField("providerIs", e.target.value)}
                />
                <input
                  className="glass-input rounded-lg px-3 py-2.5 text-sm"
                  placeholder="Exclude providers (e.g. ollama)"
                  value={form.providerNot}
                  onChange={(e) => updateField("providerNot", e.target.value)}
                />
              </div>
            )}

            {form.action === "REDACT" && (
              <input
                className="glass-input rounded-lg px-3 py-2.5 text-sm"
                placeholder="Redact entities (e.g. PERSON, EMAIL_ADDRESS)"
                value={form.redactEntities}
                onChange={(e) => updateField("redactEntities", e.target.value)}
              />
            )}
          </div>

          {/* Plain-English Policy Summary */}
          {policySummary && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
              <Info className="w-3.5 h-3.5 text-violet-400 shrink-0 mt-0.5" />
              <p className="text-xs text-slate-400">{policySummary}</p>
            </div>
          )}

          {error && <FeedbackBanner message={error} variant="error" onClose={() => setError(null)} />}
          {success && <FeedbackBanner message={success} variant="success" onClose={() => setSuccess(null)} />}

          <div className="flex flex-wrap gap-2">
            <Button onClick={savePolicy} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {form.id ? "Update Policy" : "Create Policy"}
            </Button>
            <Button variant="outline" onClick={() => setForm(EMPTY_FORM)}>
              Reset
            </Button>
          </div>

          {/* Policy Test */}
          <div className="border-t border-white/[0.06] pt-4">
            <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-3">Policy Test</h3>
            <Button size="sm" variant="outline" onClick={runPolicyTest} disabled={testLoading}>
              <FlaskConical className="w-3 h-3" />
              {testLoading ? "Running..." : "Run Test Case"}
            </Button>
            {testOutput && (
              <div className="text-sm text-slate-300 mt-2 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                {testOutput}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
