export interface SpeakerSettings {
  gender: 'male' | 'female';
  age: 'adult' | 'elderly' | 'young';
  voice_description?: string;
  ref_audio_path?: string;
  ref_text?: string;
  engine?: string;
  language?: string;
}

export interface NoiseSettings {
  enabled: boolean;
  types: Record<string, boolean>;
  intensity: number;
}

export interface Consultation {
  id: string;
  name: string;
  script_path?: string;
  raw_script?: string;
  status: 'queued' | 'processing' | 'done' | 'error';
  created_at: string;
  updated_at: string;
  seed: number;
  language: string;
  engine: string;
  noise_settings: NoiseSettings;
  speaker_settings: Record<string, SpeakerSettings>;
  output_dir?: string;
  error_message?: string;
  total_utterances: number;
  completed_utterances: number;
  batch_id?: string;
  utterances?: Utterance[];
}

export interface Utterance {
  id: string;
  consultation_id: string;
  speaker: string;
  text: string;
  line_number: number;
  status: 'queued' | 'processing' | 'done' | 'error';
  audio_path?: string;
  duration_seconds?: number;
  engine: string;
  voice_description?: string;
  ref_audio_path?: string;
  ref_text?: string;
  language: string;
  error_message?: string;
}

export interface ProgressInfo {
  total: number;
  done: number;
  error: number;
  processing: number;
  queued: number;
  percent: number;
  is_current: boolean;
  status: 'queued' | 'processing' | 'done' | 'error';
}

export interface ParseResult {
  turns: { speaker: string; text: string; line_number: number }[];
  speakers: string[];
  detected_language: string;
  total_turns: number;
}

export interface HealthInfo {
  status: string;
  engines: { parler: boolean; indicf5: boolean };
  device: string;
  runner_alive: boolean;
  current_job: string | null;
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers || {});
  return fetch(url, { ...init, headers });
}

export const api = {


  async getHealth(): Promise<HealthInfo> {
    const res = await authFetch('/api/health');
    return res.json();
  },

  async parseScript(file?: File, script?: string): Promise<ParseResult> {
    const fd = new FormData();
    if (file) {
      fd.append('file', file);
    } else if (script) {
      fd.append('script', script);
    } else {
      throw new Error('Either file or script must be provided');
    }
    const res = await authFetch('/api/parse', {
      method: 'POST',
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to parse script' }));
      throw new Error(err.detail || 'Failed to parse script');
    }
    return res.json();
  },

  async createConsultation(params: {
    name: string;
    script?: string;
    file?: File;
    language: string;
    engine: string;
    seed?: number;
    speaker_settings: Record<string, Partial<SpeakerSettings>>;
    noise_settings: NoiseSettings;
    randomize?: boolean;
  }): Promise<{ id: string; name: string; total_utterances: number; seed: number }> {
    const fd = new FormData();
    if (params.file) {
      fd.append('file', params.file);
    }
    
    const requestJson = {
      name: params.name,
      script: params.script,
      language: params.language,
      engine: params.engine,
      seed: params.seed,
      speaker_settings: params.speaker_settings,
      noise_settings: params.noise_settings,
      randomize: params.randomize,
    };
    
    fd.append('request_json', JSON.stringify(requestJson));
 
    const res = await authFetch('/api/consultations', {
      method: 'POST',
      body: fd,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create consultation' }));
      throw new Error(err.detail || 'Failed to create consultation');
    }
    return res.json();
  },
 
  async listConsultations(): Promise<Consultation[]> {
    const res = await authFetch('/api/consultations');
    if (!res.ok) {
      throw new Error('Failed to load consultations');
    }
    return res.json();
  },
 
  async getConsultation(cid: string): Promise<Consultation> {
    const res = await authFetch(`/api/consultations/${cid}`);
    if (!res.ok) throw new Error('Consultation not found');
    return res.json();
  },
 
  async deleteConsultation(cid: string): Promise<{ deleted: string }> {
    const res = await authFetch(`/api/consultations/${cid}`, {
      method: 'DELETE',
    });
    return res.json();
  },
 
  async getProgress(cid: string): Promise<ProgressInfo> {
    const res = await authFetch(`/api/consultations/${cid}/progress`);
    return res.json();
  },
 
  async getVoiceProfiles(): Promise<Record<string, string>> {
    const res = await authFetch('/api/voice-profiles');
    return res.json();
  },
 
  async getNoiseTypes(): Promise<Record<string, string>> {
    const res = await authFetch('/api/noise-types');
    return res.json();
  },
 
  async createBatch(params: {
    name: string;
    scripts: { name: string; script: string; language?: string }[];
    engine: string;
    seed?: number;
    speaker_settings: Record<string, Partial<SpeakerSettings>>;
    noise_settings: NoiseSettings;
    randomize?: boolean;
  }): Promise<{ batch_id: string; consultation_ids: string[]; total: number }> {
    const res = await authFetch('/api/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to create batch job' }));
      throw new Error(err.detail || 'Failed to create batch job');
    }
    return res.json();
  },
 
  async listBatches(): Promise<any[]> {
    const res = await authFetch('/api/batch');
    return res.json();
  },
 
  async getBatch(bid: string): Promise<any> {
    const res = await authFetch(`/api/batch/${bid}`);
    return res.json();
  },
};
