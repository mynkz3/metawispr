export type Stage = 'queued' | 'preparing' | 'transcribing' | 'transcribed' | 'refining' | 'documenting' | 'complete' | 'failed';
export type Meeting = {
  id: string; title: string; filename: string; glossary: string; created_at: string; updated_at: string;
  stage: Stage; duration_seconds: number | null; processed_audio_seconds: number;
  failed_stage: Stage | null; error: string | null; retryable: boolean;
  llm_completed_calls: number; target: 'transcribed' | 'complete';
};
export type Segment = { id: string; start: number; end: number; text: string };
export type Evidence = { segment_id: string; quote: string };
export type Fact = { text: string; evidence: Evidence[] };
export type Task = Fact & { owner: string | null; deadline: string | null };
export type Edit = { segment_id: string; original: string; replacement: string; reason: string; start?: number; end?: number };
export type View = {
  meeting: Meeting;
  raw: { segments: Segment[]; warnings: string[] } | null;
  refined: { segments: Segment[]; accepted: Edit[]; rejected: { edit: Edit; rejection: string }[]; warnings: string[] } | null;
  document: {
    unavailable_sections?: ('tasks' | 'decisions')[];
    record: { summary: Fact[]; topics: { title: string; points: Fact[] }[]; decisions: Fact[]; tasks: Task[]; uncertainties: string[] };
    revision_audit: Fact[]; warnings: string[];
  } | null;
};
export type Health = {
  transcription_ready: boolean; conversion_ready: boolean; llm_ready: boolean; llm_error: string | null;
  limits: { upload_bytes: number; audio_seconds: number; pending_jobs: number };
};
