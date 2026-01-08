import React from 'react'

function ThoughtBubble({ action, detail, ago, status }) {
  if (!action && !detail) {
    return null
  }

  const getBubbleClass = () => {
    switch (status) {
      case 'healthy':
        return 'bubble-healthy'
      case 'degraded':
        return 'bubble-warning'
      case 'down':
        return 'bubble-error'
      default:
        return ''
    }
  }

  return (
    <div className={`thought-bubble ${getBubbleClass()}`}>
      <div className="bubble-content">
        <p className="bubble-action">{action}</p>
        {detail && (
          <p className="bubble-detail">{detail}</p>
        )}
        {ago && (
          <p className="bubble-ago">{ago}</p>
        )}
      </div>

      {/* Bubble tail (the little circles) */}
      <div className="bubble-tail">
        <div className="tail-circle tail-1"></div>
        <div className="tail-circle tail-2"></div>
        <div className="tail-circle tail-3"></div>
      </div>
    </div>
  )
}

export default ThoughtBubble
