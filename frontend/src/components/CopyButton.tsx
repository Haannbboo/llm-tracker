import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

export function CopyButton({
  text,
  className = 'btn-ghost',
  style,
  idleLabel,
  copiedLabel,
  onCopied,
  timeoutMs = 1500,
}: {
  text: string
  className?: string
  style?: CSSProperties
  idleLabel: ReactNode
  copiedLabel: ReactNode
  onCopied?: () => void
  timeoutMs?: number
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    void navigator.clipboard.writeText(text)
      .then(() => {
        setCopied(true)
        onCopied?.()
        setTimeout(() => setCopied(false), timeoutMs)
      })
  }

  return (
    <button
      className={`${className}${copied ? ' btn-copy-clicked' : ''}`}
      onClick={handleCopy}
      style={style}
    >
      {copied ? copiedLabel : idleLabel}
    </button>
  )
}

export function copyTextToClipboard(text: string, onCopy?: (msg: string) => void) {
  void navigator.clipboard.writeText(text).then(() => {
    onCopy?.('✓ Copied to clipboard')
  })
}

export function ClickToCopy({ text, children, onCopy }: { text: string, children: React.ReactNode, onCopy?: (msg: string) => void }) {
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    copyTextToClipboard(text, onCopy);
  };

  return (
    <span className="click-to-copy" onClick={handleCopy} title="Click to copy">
      {children}
    </span>
  );
}
