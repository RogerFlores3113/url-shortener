import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/router";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function formatDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function truncate(str, max = 60) {
  return str.length > max ? str.slice(0, max) + "…" : str;
}

export default function Dashboard() {
  const router = useRouter();
  const userId = router.query.user_id || "";

  const [links, setLinks] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | empty | populated | error
  const [includeExpired, setIncludeExpired] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchLinks = useCallback(
    async (expired) => {
      if (!userId) return;
      setStatus("loading");
      try {
        const qs = expired ? `&include_expired=true` : "";
        const res = await fetch(`${API_URL}/api/links?user_id=${encodeURIComponent(userId)}${qs}`);
        if (!res.ok) throw new Error("API error");
        const data = await res.json();
        setLinks(data.links);
        setStatus(data.links.length === 0 ? "empty" : "populated");
      } catch {
        setStatus("error");
      }
    },
    [userId]
  );

  useEffect(() => {
    if (router.isReady) fetchLinks(includeExpired);
  }, [router.isReady, fetchLinks, includeExpired]);

  async function handleCreate(e) {
    e.preventDefault();
    setFormError("");
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/links`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, long_url: newUrl }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFormError(data.error || "Failed to create link");
        return;
      }
      setLinks((prev) => [data, ...prev]);
      setNewUrl("");
      setStatus("populated");
    } catch {
      setFormError("Failed to create link");
    } finally {
      setSubmitting(false);
    }
  }

  const now = new Date();

  return (
    <main style={styles.page}>
      <h1 style={styles.title}>Dashboard — {userId}</h1>

      <form onSubmit={handleCreate} style={styles.form}>
        <label style={styles.label} htmlFor="newUrl">Shorten a URL</label>
        <div style={styles.row}>
          <input
            id="newUrl"
            type="text"
            value={newUrl}
            onChange={(e) => { setNewUrl(e.target.value); setFormError(""); }}
            placeholder="https://example.com/very/long/url"
            style={{ ...styles.input, flex: 1 }}
          />
          <button type="submit" disabled={submitting} style={styles.button}>
            {submitting ? "Creating…" : "Create"}
          </button>
        </div>
        {formError && <p style={styles.error}>{formError}</p>}
      </form>

      <div style={styles.toggleRow}>
        <label style={{ cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={includeExpired}
            onChange={(e) => setIncludeExpired(e.target.checked)}
            style={{ marginRight: 6 }}
          />
          Show expired links
        </label>
      </div>

      {status === "loading" && <p>Loading…</p>}
      {status === "error" && <p style={styles.error}>Failed to load links</p>}
      {status === "empty" && <p style={{ color: "#888" }}>No links yet</p>}
      {status === "populated" && (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Short Code</th>
              <th style={styles.th}>Long URL</th>
              <th style={styles.th}>Expires</th>
            </tr>
          </thead>
          <tbody>
            {links.map((link) => {
              const expired = new Date(link.expires_at) <= now;
              return (
                <tr key={link.short_code} style={expired ? styles.expiredRow : {}}>
                  <td style={styles.td}>
                    <a
                      href={`${API_URL}/${link.short_code}`}
                      target="_blank"
                      rel="noreferrer"
                      style={expired ? styles.expiredLink : styles.link}
                    >
                      {link.short_code}
                    </a>
                  </td>
                  <td style={styles.td} title={link.long_url}>
                    {truncate(link.long_url)}
                  </td>
                  <td style={styles.td}>{formatDate(link.expires_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </main>
  );
}

const styles = {
  page: { fontFamily: "monospace", maxWidth: 900, margin: "40px auto", padding: "0 16px" },
  title: { marginBottom: 24 },
  form: { display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 },
  label: { fontWeight: "bold" },
  row: { display: "flex", gap: 8 },
  input: { padding: "8px 10px", fontSize: 14, border: "1px solid #ccc", borderRadius: 4 },
  button: {
    padding: "8px 16px",
    fontSize: 14,
    cursor: "pointer",
    background: "#111",
    color: "#fff",
    border: "none",
    borderRadius: 4,
  },
  error: { color: "red", margin: 0, fontSize: 14 },
  toggleRow: { marginBottom: 16 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", borderBottom: "2px solid #ccc", padding: "6px 10px" },
  td: { padding: "6px 10px", borderBottom: "1px solid #eee", verticalAlign: "top" },
  expiredRow: { opacity: 0.45 },
  link: { color: "#0070f3" },
  expiredLink: { color: "#aaa" },
};
