/** Internal error hierarchy — never surfaced to SDK callers */

export class LoreAiError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
  ) {
    super(message);
    this.name = "LoreAiError";
  }
}

export class AuthError extends LoreAiError {
  constructor(message = "Invalid or missing API key") {
    super(message, 401);
    this.name = "AuthError";
  }
}

export class RateLimitError extends LoreAiError {
  constructor(public readonly retryAfterMs?: number) {
    super("Rate limit exceeded", 429);
    this.name = "RateLimitError";
  }
}

export class ServerError extends LoreAiError {
  constructor(statusCode: number, message = "Server error") {
    super(message, statusCode);
    this.name = "ServerError";
  }
}

export class NetworkError extends LoreAiError {
  constructor(cause?: unknown) {
    super(cause instanceof Error ? cause.message : "Network error");
    this.name = "NetworkError";
    if (cause instanceof Error) this.cause = cause;
  }
}

export class TimeoutError extends LoreAiError {
  constructor() {
    super("Request timed out");
    this.name = "TimeoutError";
  }
}
