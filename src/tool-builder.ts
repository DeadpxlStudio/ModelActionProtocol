// =============================================================================
// Tool Builder — The "Paved Path" for MAP-compliant tools
//
// Instead of asking developers to manually write reversal schemas,
// these helpers make it one function call:
//
//   defineRestoreTool('updateCustomer', schema, fn)    → auto GET before PUT
//   defineCompensateTool('chargeCard', schema, fn, compensatingFn)
//   defineEscalateTool('wireTransfer', schema, fn, 'treasury@acme.com')
//
// This is the adoption engine. The protocol is the standard.
// The tool builders eliminate the friction tax.
// =============================================================================

import type { z } from "zod";
import type { MAPTool, ReversalSchema } from "./protocol.js";

/**
 * Define a generic MAP-compliant tool with an explicit reversal schema.
 */
export function defineTool<TInput, TOutput>(options: {
  name: string;
  description: string;
  inputSchema: z.ZodType<TInput>;
  execute: (input: TInput) => Promise<TOutput>;
  reversal: ReversalSchema;
}): MAPTool<TInput, TOutput> {
  return {
    name: options.name,
    description: options.description,
    inputSchema: options.inputSchema,
    execute: options.execute,
    reversal: options.reversal,
  };
}

/**
 * Define a RESTORE tool — for CRUD APIs with GET + PUT.
 *
 * Before every write, MAP captures the current state via the capture function.
 * On rollback, MAP pushes the original state back via the restore function.
 *
 * Example:
 *   defineRestoreTool({
 *     name: 'updateCustomer',
 *     schema, execute,
 *     capture: (input) => api.getCustomer(input.id),
 *     restore: (captured) => api.updateCustomer(captured),
 *   })
 */
export function defineRestoreTool<TInput, TOutput, TCaptured = unknown>(options: {
  name: string;
  description: string;
  inputSchema: z.ZodType<TInput>;
  execute: (input: TInput) => Promise<TOutput>;
  /** Capture the current state before the action (e.g., GET request) */
  capture: (input: TInput) => Promise<TCaptured>;
  /** Restore the captured state on rollback (e.g., PUT request) */
  restore: (captured: TCaptured) => Promise<void>;
  captureMethod?: string;
}): MAPTool<TInput, TOutput> & {
  capture: (input: TInput) => Promise<TCaptured>;
  restore: (captured: TCaptured) => Promise<void>;
} {
  return {
    name: options.name,
    description: options.description,
    inputSchema: options.inputSchema,
    execute: options.execute,
    capture: options.capture,
    restore: options.restore,
    reversal: {
      strategy: "RESTORE",
      captureMethod: options.captureMethod ?? `GET /${options.name}/:id`,
      description: `Capture state before ${options.name}, restore on rollback`,
    },
  };
}

/**
 * Define a COMPENSATE tool — for systems that don't allow hard deletes.
 *
 * Maps a forward action to its compensating action.
 * Example: duplicate invoice → issue credit memo.
 *
 * Example:
 *   defineCompensateTool({
 *     name: 'createInvoice',
 *     schema, execute,
 *     compensate: (input, output) => api.issueCreditMemo(output.invoiceId),
 *   })
 */
export function defineCompensateTool<TInput, TOutput>(options: {
  name: string;
  description: string;
  inputSchema: z.ZodType<TInput>;
  execute: (input: TInput) => Promise<TOutput>;
  /** The compensating action to reverse this tool's effect */
  compensate: (input: TInput, output: TOutput) => Promise<unknown>;
  /** Human-readable description of the compensation */
  compensationDescription?: string;
}): MAPTool<TInput, TOutput> & {
  compensate: (input: TInput, output: TOutput) => Promise<unknown>;
} {
  return {
    name: options.name,
    description: options.description,
    inputSchema: options.inputSchema,
    execute: options.execute,
    compensate: options.compensate,
    reversal: {
      strategy: "COMPENSATE",
      description: options.compensationDescription ??
        `Compensating action for ${options.name}`,
    },
  };
}

/**
 * Define an ESCALATE tool — for irreversible actions.
 *
 * MAP intercepts before execution, places the action in "Pending" state,
 * and routes to a human for approval. The action only executes after
 * explicit human approval.
 *
 * Example:
 *   defineEscalateTool({
 *     name: 'wireTransfer',
 *     schema, execute,
 *     approver: 'treasury@acme.com',
 *   })
 */
export function defineEscalateTool<TInput, TOutput>(options: {
  name: string;
  description: string;
  inputSchema: z.ZodType<TInput>;
  execute: (input: TInput) => Promise<TOutput>;
  /** Who should approve this action (role, email, or group) */
  approver: string;
  /** Human-readable description of why this needs escalation */
  escalationReason?: string;
}): MAPTool<TInput, TOutput> {
  return {
    name: options.name,
    description: options.description,
    inputSchema: options.inputSchema,
    execute: options.execute,
    reversal: {
      strategy: "ESCALATE",
      approver: options.approver,
      description: options.escalationReason ??
        `${options.name} is irreversible and requires human approval`,
    },
  };
}
