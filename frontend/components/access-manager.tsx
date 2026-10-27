"use client";

import { useState } from "react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { Busy, ErrorNotice, Modal } from "@/components/ui";
import {
  Users,
  Building2,
  ShieldCheck,
  Plus,
  Save,
  Check,
  Lock,
  Edit2,
  LayoutDashboard,
  Inbox,
  Layers,
  FileCheck2,
  Upload,
  Settings,
} from "lucide-react";
import type { Branch, User, RolePermissionsMap } from "@/lib/types";

const ALL_MENUS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "cases", label: "Customer Cases", icon: Layers },
  { id: "reports", label: "Kertas Kerja (Reports)", icon: FileCheck2 },
  { id: "upload", label: "Upload Documents", icon: Upload },
  { id: "settings", label: "Configuration", icon: Settings },
];

const BRANCH_TIERS = [
  { id: "KP", label: "Kantor Pusat (Head Office)" },
  { id: "KCU", label: "Kantor Cabang Utama (Main Branch)" },
  { id: "KCP", label: "Kantor Cabang Pembantu (Sub-Branch)" },
  { id: "SENTRA_VALAS", label: "Sentra Operasi Valas / Trade Finance Hub" },
];

const FALLBACK_ROLES: RolePermissionsMap = {
  bank_admin: { label: "Bank Administrator", menus: ["overview", "inbox", "cases", "reports", "upload", "settings"], can_edit_settings: true, can_override_cases: true, can_manage_users: true },
  branch_admin: { label: "Branch Administrator", menus: ["overview", "inbox", "cases", "reports", "upload", "settings"], can_edit_settings: true, can_override_cases: true, can_manage_users: false },
  officer: { label: "Branch Officer", menus: ["overview", "inbox", "cases", "upload"], can_edit_settings: false, can_override_cases: false, can_manage_users: false },
  reviewer: { label: "Document Reviewer / Checker", menus: ["overview", "inbox", "cases", "reports"], can_edit_settings: false, can_override_cases: true, can_manage_users: false },
  auditor: { label: "Compliance Auditor", menus: ["overview", "cases", "reports"], can_edit_settings: false, can_override_cases: false, can_manage_users: false },
};

export function AccessManager() {
  const { user, notify } = usePlatform();
  const [subTab, setSubTab] = useState<"users" | "roles" | "branches">("users");

  const { data: branches, refresh: refreshBranches, error: branchError } = useData<Branch[]>("/branches", 0);
  const { data: users, refresh: refreshUsers, error: userError } = useData<User[]>("/users", 0);
  const { data: rolePermissions, refresh: refreshRolePerms, error: permError } = useData<RolePermissionsMap>(
    "/access/role-permissions",
    0
  );

  // Dialog states
  const [branchModal, setBranchModal] = useState<Branch | "new" | null>(null);
  const [userModal, setUserModal] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Role permissions draft state
  const [draftPerms, setDraftPerms] = useState<RolePermissionsMap | null>(null);

  const activePerms = draftPerms || rolePermissions;

  const toggleRoleMenu = (roleKey: string, menuId: string) => {
    if (!activePerms) return;
    const currentRole = activePerms[roleKey] || {
      label: roleKey,
      menus: [],
      can_edit_settings: false,
      can_override_cases: false,
      can_manage_users: false,
    };
    const currentMenus = currentRole.menus || [];
    const updatedMenus = currentMenus.includes(menuId)
      ? currentMenus.filter((m) => m !== menuId)
      : [...currentMenus, menuId];

    setDraftPerms({
      ...activePerms,
      [roleKey]: {
        ...currentRole,
        menus: updatedMenus,
      },
    });
  };

  const toggleRoleAction = (roleKey: string, actionKey: "can_edit_settings" | "can_override_cases" | "can_manage_users") => {
    if (!activePerms) return;
    const currentRole = activePerms[roleKey] || {
      label: roleKey,
      menus: [],
      can_edit_settings: false,
      can_override_cases: false,
      can_manage_users: false,
    };
    setDraftPerms({
      ...activePerms,
      [roleKey]: {
        ...currentRole,
        [actionKey]: !currentRole[actionKey],
      },
    });
  };

  const saveRolePermissions = async () => {
    if (!draftPerms) return;
    setPending(true);
    try {
      await api("/access/role-permissions", {
        method: "PUT",
        body: JSON.stringify({ roles: draftPerms }),
      });
      notify("Role permissions updated successfully.");
      setDraftPerms(null);
      await refreshRolePerms();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to update permissions", "error");
    } finally {
      setPending(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Sub-tab navigation */}
      <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid var(--border)", paddingBottom: "0.5rem" }}>
        <button
          type="button"
          className={subTab === "users" ? "primary" : "secondary"}
          onClick={() => setSubTab("users")}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}
        >
          <Users size={16} /> Users & Assignments
        </button>
        <button
          type="button"
          className={subTab === "roles" ? "primary" : "secondary"}
          onClick={() => setSubTab("roles")}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}
        >
          <ShieldCheck size={16} /> Role Menu Permission Matrix
        </button>
        <button
          type="button"
          className={subTab === "branches" ? "primary" : "secondary"}
          onClick={() => setSubTab("branches")}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}
        >
          <Building2 size={16} /> Branch Capabilities & Menus
        </button>
      </div>

      {(branchError || userError || permError) && (
        <ErrorNotice message={branchError || userError || permError || ""} />
      )}

      {/* VIEW 1: USERS */}
      {subTab === "users" && (
        <section className="panel settings-card">
          <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Banking Users & Memberships</h2>
              <p style={{ margin: "0.2rem 0 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Active staff accounts, role designations, and assigned branch memberships.
              </p>
            </div>
            <button className="primary" onClick={() => { setErrorMsg(""); setUserModal(true); }} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
              <Plus size={16} /> Add User
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {users?.map((u) => {
              const roleInfo = activePerms?.[u.role];
              return (
                <div
                  key={u.id}
                  className="access-row"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.85rem 1rem",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    background: "var(--bg-panel, #ffffff)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                    <span className="avatar" style={{ width: 36, height: 36, fontSize: "0.95rem" }}>
                      {u.name[0]}
                    </span>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <strong>{u.name}</strong>
                        <span style={{ fontSize: "0.75rem", background: "#f1f5f9", padding: "0.1rem 0.45rem", borderRadius: "4px", color: "var(--text-muted)" }}>
                          {u.email}
                        </span>
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                        Branches:{" "}
                        {u.branches
                          .map((id) => branches?.find((b) => b.id === id)?.name || id.slice(0, 8))
                          .join(", ")}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    <span className="role-tag" style={{ textTransform: "capitalize", fontWeight: 600 }}>
                      {roleInfo?.label || u.role.replaceAll("_", " ")}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* VIEW 2: ROLE MENU MATRIX */}
      {subTab === "roles" && (
        <section className="panel settings-card">
          <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Role Access Menu Setup (RBAC)</h2>
              <p style={{ margin: "0.2rem 0 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Configure navigation menus and authorization privileges per bank operational role.
              </p>
            </div>
            {draftPerms && (
              <button
                className="primary"
                onClick={saveRolePermissions}
                disabled={pending}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              >
                <Save size={16} /> {pending ? "Saving…" : "Save Role Matrix"}
              </button>
            )}
          </div>

          <div style={{ overflowX: "auto" }}>
            <table className="corporate-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ background: "var(--bg-muted, #f8fafc)", textAlign: "left", borderBottom: "2px solid var(--border)" }}>
                  <th style={{ padding: "0.75rem 1rem", minWidth: 160 }}>Operational Role</th>
                  {ALL_MENUS.map((m) => (
                    <th key={m.id} style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>
                      {m.label}
                    </th>
                  ))}
                  <th style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>Edit Config</th>
                  <th style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>Case Overrides</th>
                  <th style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>Manage Users</th>
                </tr>
              </thead>
              <tbody>
                {activePerms &&
                  Object.entries(activePerms).map(([roleKey, conf]) => {
                    const isBankAdmin = roleKey === "bank_admin";
                    return (
                      <tr key={roleKey} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "0.85rem 1rem" }}>
                          <strong>{conf.label || roleKey}</strong>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>code: {roleKey}</div>
                        </td>
                        {ALL_MENUS.map((m) => {
                          const checked = conf.menus?.includes(m.id);
                          return (
                            <td key={m.id} style={{ textAlign: "center", padding: "0.5rem" }}>
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={isBankAdmin && m.id === "settings"}
                                onChange={() => toggleRoleMenu(roleKey, m.id)}
                              />
                            </td>
                          );
                        })}
                        <td style={{ textAlign: "center", padding: "0.5rem" }}>
                          <input
                            type="checkbox"
                            checked={conf.can_edit_settings}
                            disabled={isBankAdmin}
                            onChange={() => toggleRoleAction(roleKey, "can_edit_settings")}
                          />
                        </td>
                        <td style={{ textAlign: "center", padding: "0.5rem" }}>
                          <input
                            type="checkbox"
                            checked={conf.can_override_cases}
                            onChange={() => toggleRoleAction(roleKey, "can_override_cases")}
                          />
                        </td>
                        <td style={{ textAlign: "center", padding: "0.5rem" }}>
                          <input
                            type="checkbox"
                            checked={conf.can_manage_users}
                            disabled={isBankAdmin}
                            onChange={() => toggleRoleAction(roleKey, "can_manage_users")}
                          />
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* VIEW 3: BRANCH CAPABILITIES & MENUS */}
      {subTab === "branches" && (
        <section className="panel settings-card">
          <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h2 style={{ margin: 0 }}>Branch Tier & Menu Scoping</h2>
              <p style={{ margin: "0.2rem 0 0", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Control which branches can access specific system menus and high-risk banking workflows.
              </p>
            </div>
            {user?.role === "bank_admin" && (
              <button
                className="primary"
                onClick={() => { setErrorMsg(""); setBranchModal("new"); }}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              >
                <Plus size={16} /> Add Branch
              </button>
            )}
          </div>

          <div style={{ display: "grid", gap: "0.75rem" }}>
            {branches?.map((b) => {
              const tierObj = BRANCH_TIERS.find((t) => t.id === b.tier);
              const allowedMenus = b.menus || ALL_MENUS.map((m) => m.id);
              return (
                <div
                  key={b.id}
                  style={{
                    padding: "1rem 1.25rem",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    background: "var(--bg-panel, #ffffff)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                    <span className="branch-avatar" style={{ width: 40, height: 40, display: "flex", alignItems: "center", justifyContent: "center", background: "#f1f5f9", borderRadius: "8px", fontWeight: 700, fontSize: "0.95rem" }}>
                      {b.code.slice(0, 2)}
                    </span>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <strong style={{ fontSize: "1rem" }}>{b.name}</strong>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", background: "rgba(0,0,0,0.04)", padding: "0.1rem 0.4rem", borderRadius: "4px" }}>
                          {b.code}
                        </span>
                        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#1e40af", background: "#dbeafe", padding: "0.15rem 0.5rem", borderRadius: "12px" }}>
                          {tierObj?.label || b.tier || "KCU"}
                        </span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.35rem", flexWrap: "wrap" }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Allowed Menus:</span>
                        {ALL_MENUS.filter((m) => allowedMenus.includes(m.id)).map((m) => (
                          <span
                            key={m.id}
                            style={{
                              fontSize: "0.7rem",
                              background: "#f8fafc",
                              border: "1px solid #e2e8f0",
                              padding: "0.1rem 0.4rem",
                              borderRadius: "4px",
                              color: "#334155",
                            }}
                          >
                            {m.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {user?.role === "bank_admin" && (
                    <button
                      className="secondary"
                      onClick={() => { setErrorMsg(""); setBranchModal(b); }}
                      style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", padding: "0.35rem 0.65rem" }}
                    >
                      <Edit2 size={14} /> Configure Scope
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* MODAL: ADD / EDIT BRANCH */}
      {branchModal && (
        <BranchModal
          branch={branchModal === "new" ? null : branchModal}
          onClose={() => setBranchModal(null)}
          onSaved={async () => {
            setBranchModal(null);
            await refreshBranches();
          }}
        />
      )}

      {/* MODAL: ADD USER */}
      {userModal && (
        <Modal title="Add Bank User" onClose={() => setUserModal(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setPending(true);
              setErrorMsg("");
              const form = new FormData(e.currentTarget);
              try {
                await api("/users", {
                  method: "POST",
                  body: JSON.stringify({
                    email: form.get("email"),
                    name: form.get("name"),
                    password: form.get("password"),
                    role: form.get("role"),
                    branches: form.getAll("branches"),
                  }),
                });
                notify("User created.");
                setUserModal(false);
                await refreshUsers();
              } catch (err) {
                setErrorMsg(err instanceof Error ? err.message : "Unable to save user.");
              } finally {
                setPending(false);
              }
            }}
          >
            {errorMsg && <ErrorNotice message={errorMsg} />}
            <label>
              Full name
              <input name="name" required />
            </label>
            <label>
              Email address
              <input name="email" type="email" required />
            </label>
            <label>
              Initial password
              <input name="password" type="password" autoComplete="new-password" minLength={12} required />
            </label>
            <label>
              Role
              <select name="role" defaultValue="officer">
                {Object.entries((activePerms || FALLBACK_ROLES) as RolePermissionsMap).map(([key, val]) => (
                  <option key={key} value={key}>
                    {val?.label || key} ({key})
                  </option>
                ))}
              </select>
            </label>
            <label>Branch memberships</label>
            <div style={{ maxHeight: 160, overflowY: "auto", border: "1px solid var(--border)", padding: "0.5rem", borderRadius: "6px" }}>
              {branches?.map((b) => (
                <label className="checkbox-label compact" key={b.id} style={{ display: "flex", alignItems: "center", gap: "0.4rem", margin: "0.25rem 0" }}>
                  <input type="checkbox" name="branches" value={b.id} />
                  {b.name} ({b.code})
                </label>
              ))}
            </div>
            <div className="modal-actions" style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
              <button type="button" className="secondary" onClick={() => setUserModal(false)}>
                Cancel
              </button>
              <button className="primary" disabled={pending}>
                {pending ? "Saving…" : "Create User"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function BranchModal({
  branch,
  onClose,
  onSaved,
}: {
  branch: Branch | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { notify } = usePlatform();
  const [name, setName] = useState(branch?.name || "");
  const [code, setCode] = useState(branch?.code || "");
  const [tier, setTier] = useState(branch?.tier || "KCU");
  const [menus, setMenus] = useState<string[]>(branch?.menus || ALL_MENUS.map((m) => m.id));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const toggleMenu = (id: string) => {
    setMenus((prev) => (prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError("");
    try {
      if (branch) {
        await api(`/branches/${branch.id}`, {
          method: "PUT",
          body: JSON.stringify({ name, tier, menus }),
        });
        notify(`Branch ${code} updated.`);
      } else {
        await api("/branches", {
          method: "POST",
          body: JSON.stringify({ code, name, tier, menus }),
        });
        notify(`Branch ${code} created.`);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save branch.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal title={branch ? `Configure Branch: ${branch.name}` : "Add New Branch"} onClose={onClose}>
      <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {error && <ErrorNotice message={error} />}
        <label>
          Branch Name
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. KCU Sudirman Jakarta" />
        </label>

        <label>
          Branch Code
          <input
            required
            disabled={!!branch}
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="e.g. JKT01"
          />
        </label>

        <label>
          Branch Tier & Operational Classification
          <select value={tier} onChange={(e) => setTier(e.target.value)}>
            {BRANCH_TIERS.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <div>
          <label style={{ display: "block", marginBottom: "0.4rem", fontWeight: 600 }}>
            Enabled Menus for this Branch:
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            {ALL_MENUS.map((m) => (
              <label
                key={m.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  fontSize: "0.85rem",
                  background: "#f8fafc",
                  padding: "0.4rem 0.6rem",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                }}
              >
                <input type="checkbox" checked={menus.includes(m.id)} onChange={() => toggleMenu(m.id)} />
                {m.label}
              </label>
            ))}
          </div>
        </div>

        <div className="modal-actions" style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.5rem" }}>
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={pending}>
            {pending ? "Saving…" : branch ? "Update Branch" : "Create Branch"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
