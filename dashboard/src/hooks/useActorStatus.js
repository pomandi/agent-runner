import { useState, useEffect, useCallback } from 'react'

const POLL_INTERVAL = 10000 // 10 seconds

// Default actors when API is not available
const DEFAULT_ACTORS = [
  {
    name: "temporal",
    displayName: "Temporal",
    role: "Yonetmen",
    status: "loading",
    emoji: "(^_^)",
    color: "#6366f1",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "langgraph",
    displayName: "LangGraph",
    role: "Sahne Direktoru",
    status: "loading",
    emoji: "(o_o)",
    color: "#8b5cf6",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "redis",
    displayName: "Redis",
    role: "Suflor",
    status: "loading",
    emoji: "(>_<)",
    color: "#ef4444",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "qdrant",
    displayName: "Qdrant",
    role: "Arsivci",
    status: "loading",
    emoji: "(@_@)",
    color: "#f59e0b",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "postgresql",
    displayName: "PostgreSQL",
    role: "Muhasebeci",
    status: "loading",
    emoji: "(._.)",
    color: "#3b82f6",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "langfuse",
    displayName: "Langfuse",
    role: "Elestirmen",
    status: "loading",
    emoji: "(~_~)",
    color: "#10b981",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "claude_sdk",
    displayName: "Claude SDK",
    role: "Beyin",
    status: "loading",
    emoji: "(*_*)",
    color: "#d946ef",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  },
  {
    name: "mcp_servers",
    displayName: "MCP Servers",
    role: "Malzemeler",
    status: "loading",
    emoji: "(+_+)",
    color: "#14b8a6",
    lastActivity: { action: "Yukleniyor...", detail: "", ago: "" }
  }
]

function useActorStatus() {
  const [actors, setActors] = useState(DEFAULT_ACTORS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/actors/status')

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()

      if (data.actors && Array.isArray(data.actors)) {
        setActors(data.actors)
        setError(null)
      }

      if (data.updated_at) {
        const date = new Date(data.updated_at)
        setLastUpdate(date.toLocaleTimeString('tr-TR'))
      }
    } catch (err) {
      console.error('Failed to fetch actor status:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // Initial fetch
    fetchStatus()

    // Set up polling
    const interval = setInterval(fetchStatus, POLL_INTERVAL)

    return () => clearInterval(interval)
  }, [fetchStatus])

  return { actors, loading, error, lastUpdate, refetch: fetchStatus }
}

export default useActorStatus
