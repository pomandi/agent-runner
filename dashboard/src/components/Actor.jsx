import React from 'react'
import ThoughtBubble from './ThoughtBubble'
import StatusIndicator from './StatusIndicator'

function Actor({ actor, index, total }) {
  const {
    name,
    displayName,
    role,
    status,
    emoji,
    color,
    lastActivity,
    metrics
  } = actor

  // Determine animation class based on status
  const getAnimationClass = () => {
    switch (status) {
      case 'healthy':
        return 'actor-idle'
      case 'degraded':
        return 'actor-worried'
      case 'down':
        return 'actor-error'
      case 'loading':
        return 'actor-loading'
      default:
        return 'actor-idle'
    }
  }

  return (
    <div
      className={`actor-container ${getAnimationClass()}`}
      style={{
        '--actor-color': color,
        '--actor-index': index,
        '--delay': `${index * 0.1}s`
      }}
    >
      {/* Thought Bubble */}
      <ThoughtBubble
        action={lastActivity?.action}
        detail={lastActivity?.detail}
        ago={lastActivity?.ago}
        status={status}
      />

      {/* Character */}
      <div className="actor-character">
        <StatusIndicator status={status} color={color} />

        {/* SVG Character */}
        <svg
          className="character-svg"
          viewBox="0 0 100 140"
          width="80"
          height="112"
        >
          {/* Head */}
          <ellipse
            cx="50"
            cy="30"
            rx="25"
            ry="28"
            fill={color}
            className="character-head"
          />

          {/* Face - emoji style */}
          <text
            x="50"
            y="38"
            textAnchor="middle"
            fontSize="18"
            fill="white"
            className="character-face"
          >
            {emoji}
          </text>

          {/* Body */}
          <path
            d="M 25 60 Q 25 55 50 55 Q 75 55 75 60 L 70 95 Q 70 100 50 100 Q 30 100 30 95 Z"
            fill={color}
            opacity="0.8"
            className="character-body"
          />

          {/* Arms */}
          <ellipse
            cx="15"
            cy="75"
            rx="8"
            ry="20"
            fill={color}
            opacity="0.7"
            className="character-arm-left"
          />
          <ellipse
            cx="85"
            cy="75"
            rx="8"
            ry="20"
            fill={color}
            opacity="0.7"
            className="character-arm-right"
          />

          {/* Legs */}
          <rect
            x="32"
            y="95"
            width="12"
            height="35"
            rx="5"
            fill={color}
            opacity="0.6"
            className="character-leg-left"
          />
          <rect
            x="56"
            y="95"
            width="12"
            height="35"
            rx="5"
            fill={color}
            opacity="0.6"
            className="character-leg-right"
          />

          {/* Feet */}
          <ellipse
            cx="38"
            cy="132"
            rx="10"
            ry="5"
            fill={color}
            opacity="0.5"
          />
          <ellipse
            cx="62"
            cy="132"
            rx="10"
            ry="5"
            fill={color}
            opacity="0.5"
          />
        </svg>
      </div>

      {/* Name and Role */}
      <div className="actor-info">
        <h3 className="actor-name" style={{ color }}>
          {displayName}
        </h3>
        <p className="actor-role">{role}</p>
      </div>

      {/* Shadow */}
      <div
        className="actor-shadow"
        style={{ backgroundColor: color }}
      />
    </div>
  )
}

export default Actor
