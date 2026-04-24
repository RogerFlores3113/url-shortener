import { useState } from "react";
import { useRouter } from "next/router";

export default function Home() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = username.trim();
    if (!trimmed) {
      setError("Username is required");
      return;
    }
    router.push(`/dashboard?user_id=${encodeURIComponent(trimmed)}`);
  }

  return (
    <main style={styles.page}>
      <h1 style={styles.title}>URL Shortener</h1>
      <form onSubmit={handleSubmit} style={styles.form}>
        <label style={styles.label} htmlFor="username">
          Username
        </label>
        <input
          id="username"
          type="text"
          value={username}
          onChange={(e) => {
            setUsername(e.target.value);
            setError("");
          }}
          placeholder="Enter your username"
          style={styles.input}
        />
        {error && <p style={styles.error}>{error}</p>}
        <button type="submit" style={styles.button}>
          Go to Dashboard
        </button>
      </form>
    </main>
  );
}

const styles = {
  page: {
    fontFamily: "monospace",
    maxWidth: 480,
    margin: "80px auto",
    padding: "0 16px",
  },
  title: { marginBottom: 32 },
  form: { display: "flex", flexDirection: "column", gap: 8 },
  label: { fontWeight: "bold" },
  input: { padding: "8px 10px", fontSize: 16, border: "1px solid #ccc", borderRadius: 4 },
  error: { color: "red", margin: 0, fontSize: 14 },
  button: {
    marginTop: 8,
    padding: "10px 16px",
    fontSize: 16,
    cursor: "pointer",
    background: "#111",
    color: "#fff",
    border: "none",
    borderRadius: 4,
  },
};
