import { useState, type Dispatch, type SetStateAction } from 'react'
import type { RequestLogColumnId } from '../hooks/useRequestLogColumns'
import { t } from '../i18n/index.ts'

type RequestLogColumn = {
  id: RequestLogColumnId
  label: string
}

type Props = {
  columns: RequestLogColumn[]
  selectedColumnIds: RequestLogColumnId[]
  setSelectedColumnIds: Dispatch<SetStateAction<RequestLogColumnId[]>>
  resetColumns: () => void
}

export function RequestLogColumnsControl({
  columns,
  selectedColumnIds,
  setSelectedColumnIds,
  resetColumns,
}: Props) {
  const [isOpen, setIsOpen] = useState(false)

  const toggleColumn = (columnId: RequestLogColumnId) => {
    setSelectedColumnIds((current) => {
      if (current.includes(columnId)) {
        return current.filter((id) => id !== columnId)
      }

      return [...current, columnId]
    })
  }

  return (
    <div className="request-log-columns">
      <button
        type="button"
        className="btn-ghost request-log-columns-trigger"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
      >
        {t('Columns')}
      </button>

      {isOpen && (
        <div className="request-log-columns-menu">
          <div className="request-log-columns-list">
            {columns.map((column) => (
              <label key={column.id} className="request-log-columns-option">
                <input
                  type="checkbox"
                  checked={selectedColumnIds.includes(column.id)}
                  onChange={() => toggleColumn(column.id)}
                />
                <span>{t(column.label)}</span>
              </label>
            ))}
          </div>

          <div className="request-log-columns-actions">
            <button
              type="button"
              className="btn-ghost request-log-columns-action"
              onClick={resetColumns}
            >
              {t('Reset columns')}
            </button>
            <button
              type="button"
              className="btn-ghost request-log-columns-action"
              onClick={() => setSelectedColumnIds(columns.map((column) => column.id))}
            >
              {t('All columns')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
