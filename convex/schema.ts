import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  jobs: defineTable({
    sourceUrl: v.string(),
    status: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
    lastAttemptAt: v.optional(v.number()),
    retryAt: v.optional(v.number()),
    nextSegmentIndex: v.number(),
    uploadedCount: v.number(),
    videoId: v.optional(v.string()),
    videoTitle: v.optional(v.string()),
    segments: v.optional(
      v.array(
        v.object({
          start: v.string(),
          end: v.string(),
          title: v.string(),
        }),
      ),
    ),
    totalSegments: v.optional(v.number()),
    lastError: v.optional(v.string()),
  }),
});
