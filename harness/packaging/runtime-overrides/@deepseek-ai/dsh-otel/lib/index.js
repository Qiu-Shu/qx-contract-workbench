import { Service } from "@deepseek-ai/cordis";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
// Keep the synchronous service API while leaving unused SDKs off the startup path.
//#region lib/types/index.js
/** Cordis entry for independent ordinary-event and Session-log OTLP channels. */
/** Shared transport provider. Mounting creates no queue, identity, or network connection. */
var OTel = class extends Service {
	constructor(ctx) {
		super(ctx, "otel");
	}
	/**
	* Create an independent ordinary-event channel with count-based batching.
	* The injected consumer must drain it during its fiber disposal.
	* @param options - transport, scope, resource, queue, and diagnostic settings selected by the consumer.
	* @returns the caller-owned channel; no state is shared with other channels.
	*/
	createEventReporter(options) {
		const { EventLogReporter } = require("./reporters.js");
		return new EventLogReporter(options);
	}
	/**
	* Create an independent byte-bounded Session-log channel.
	* Authorization and redaction precede reporting; the consumer owns shutdown and its outer deadline.
	* @param options - transport, scope, resource, queue, and diagnostic settings selected by the consumer.
	* @returns the caller-owned channel, preserving complete accepted events within the request byte ceiling.
	*/
	createSessionLogReporter(options) {
		const { SessionLogReporter } = require("./reporters.js");
		return new SessionLogReporter(options);
	}
};
//#endregion
export { OTel as default };
