export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

export function statusCodeValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value)
  if (typeof value !== "string") return null

  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : null
}

export function errorObject(error: unknown): Record<string, any> | null {
  if (!error || typeof error !== "object") return null
  return error as Record<string, any>
}

export function errorName(error: unknown): string | null {
  const err = errorObject(error)
  return typeof err?.name === "string" ? err.name : null
}

export function statusCodeFromError(error: unknown): number | null {
  const err = errorObject(error)
  if (!err) return null

  const directStatus = statusCodeValue(err.statusCode)
  if (directStatus != null) return directStatus

  const data = errorObject(err.data)
  return statusCodeValue(data?.statusCode)
}
