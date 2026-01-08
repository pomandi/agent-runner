import React from 'react'

function StatusIndicator({ status, color }) {
  const getStatusColor = () => {
    switch (status) {
      case 'healthy':
        return '#22c55e' // Green
      case 'degraded':
        return '#f59e0b' // Amber
      case 'down':
        return '#ef4444' // Red
      case 'loading':
        return '#94a3b8' // Gray
      default:
        return color
    }
  }

  const getStatusLabel = () => {
    switch (status) {
      case 'healthy':
        return 'Aktif'
      case 'degraded':
        return 'Uyari'
      case 'down':
        return 'Kapali'
      case 'loading':
        return '...'
      default:
        return '?'
    }
  }

  return (
    <div className={`status-indicator status-${status}`}>
      <div
        className="status-dot"
        style={{
          backgroundColor: getStatusColor(),
          boxShadow: `0 0 10px ${getStatusColor()}, 0 0 20px ${getStatusColor()}40`
        }}
      />
      <span className="status-label">{getStatusLabel()}</span>
    </div>
  )
}

export default StatusIndicator
