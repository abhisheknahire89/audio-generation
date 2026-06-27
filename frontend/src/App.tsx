import { useState, useEffect, useRef } from 'react';
import { api } from './api';
import type {
  Consultation,
  HealthInfo,
  ParseResult,
  SpeakerSettings,
  NoiseSettings
} from './api';
import {
  Activity,
  Upload,
  Volume2,
  FileText,
  Layers,
  Trash2,
  Play,
  Pause,
  Download,
  RefreshCw,
  AlertTriangle,
  Clock,
  User,
  Plus,
  X,
  History,
  FolderArchive
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'generate' | 'batch' | 'history'>('generate');

  // Health & Engine Status
  const [health, setHealth] = useState<HealthInfo | null>(null);

  // Single Generation States
  const [name, setName] = useState('New OPD Consultation');
  const [scriptText, setScriptText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [globalEngine, setGlobalEngine] = useState<'parler' | 'indicf5'>('parler');
  const [globalLanguage, setGlobalLanguage] = useState('hi_en');
  const [globalSeed, setGlobalSeed] = useState<number>(42);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  // Speaker Settings (speaker_name -> Settings)
  const [speakerSettings, setSpeakerSettings] = useState<Record<string, SpeakerSettings>>({});

  // Noise Settings
  const [noiseSettings, setNoiseSettings] = useState<NoiseSettings>({
    enabled: false,
    types: {
      hospital_ambience: false,
      fan: false,
      ac: false,
      keyboard: false,
      phone: false,
      cough: false,
      door: false,
      chatter: false,
      opd_mix: false
    },
    intensity: 0.3
  });

  // Noise display names
  const [noiseTypes, setNoiseTypes] = useState<Record<string, string>>({});

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<any>(null);
  const [jobStartTime, setJobStartTime] = useState<number | null>(null);

  const getRemainingTimeText = () => {
    if (!jobProgress || jobProgress.status === 'done' || jobProgress.status === 'error') return null;
    const done = jobProgress.done || 0;
    const total = jobProgress.total || 0;
    const remaining = total - done;
    if (remaining <= 0) return null;

    let secondsLeft = 0;
    if (jobStartTime && done > 0) {
      const elapsedSeconds = (Date.now() - jobStartTime) / 1000;
      const avgSecPerTurn = elapsedSeconds / done;
      secondsLeft = Math.round(avgSecPerTurn * remaining);
    } else {
      const secPerTurn = globalEngine === 'indicf5' ? 40 : 4;
      secondsLeft = secPerTurn * remaining;
    }

    if (secondsLeft < 60) {
      return `Est. time remaining: ${secondsLeft}s`;
    }
    const mins = Math.floor(secondsLeft / 60);
    const secs = secondsLeft % 60;
    return `Est. time remaining: ${mins}m ${secs}s`;
  };

  // History States
  const [history, setHistory] = useState<Consultation[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [selectedHistory, setSelectedHistory] = useState<Consultation | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Batch Mode States
  const [batchName, setBatchName] = useState('Batch OPD Audio');
  const [batchScripts, setBatchScripts] = useState<{ id: string; name: string; script: string }[]>([
    { id: '1', name: 'Script 1', script: '' }
  ]);
  const [activeBatchJobId, setActiveBatchJobId] = useState<string | null>(null);
  const [batchJobProgress, setBatchJobProgress] = useState<any>(null);

  // Audio Playback
  const [playingAudioUrl, setPlayingAudioUrl] = useState<string | null>(null);
  const [currentlyPlayingId, setCurrentlyPlayingId] = useState<string | null>(null); // uid or cid + 'full'
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  // Fetch health and initial data
  useEffect(() => {
    fetchHealth();
    fetchNoiseTypes();
    fetchHistory();
    const interval = setInterval(fetchHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // Poll progress if job is active
  useEffect(() => {
    if (!activeJobId) return;

    const pollProgress = async () => {
      try {
        const progress = await api.getProgress(activeJobId);
        setJobProgress(progress);
        if ((progress.status === 'processing' || progress.status === 'queued') && !jobStartTime) {
          setJobStartTime(Date.now());
        }

        if (progress.status === 'done' || progress.status === 'error') {
          setActiveJobId(null);
          setJobStartTime(null);
          fetchHistory();
          if (selectedHistoryId === activeJobId) {
            fetchConsultationDetail(activeJobId);
          }
          if (progress.status === 'done') {
            const link = document.createElement('a');
            link.href = `/api/consultations/${activeJobId}/audio/full?download=true`;
            link.download = '';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          }
        }
      } catch (err) {
        console.error('Error polling job progress:', err);
      }
    };

    pollProgress();
    const interval = setInterval(pollProgress, 2000);
    return () => clearInterval(interval);
  }, [activeJobId]);

  // Poll batch progress if active batch is running
  useEffect(() => {
    if (!activeBatchJobId) return;

    const pollBatchProgress = async () => {
      try {
        const res = await api.getBatch(activeBatchJobId);
        setBatchJobProgress(res);

        const allDone = res.consultations.every(
          (c: any) => c.status === 'done' || c.status === 'error'
        );
        if (allDone) {
          setActiveBatchJobId(null);
          fetchHistory();
          
          const hasSuccess = res.consultations.some((c: any) => c.status === 'done');
          if (hasSuccess) {
            const link = document.createElement('a');
            link.href = `/api/batch/${activeBatchJobId}/download`;
            link.download = '';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          }
        }
      } catch (err) {
        console.error('Error polling batch progress:', err);
      }
    };

    pollBatchProgress();
    const interval = setInterval(pollBatchProgress, 3000);
    return () => clearInterval(interval);
  }, [activeBatchJobId]);

  const fetchHealth = async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch (err) {
      console.error('Failed to fetch health info:', err);
    }
  };

  const fetchNoiseTypes = async () => {
    try {
      const data = await api.getNoiseTypes();
      setNoiseTypes(data);
    } catch (err) {
      console.error('Failed to fetch noise types:', err);
    }
  };

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const data = await api.listConsultations();
      setHistory(data);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const fetchConsultationDetail = async (cid: string) => {
    try {
      const data = await api.getConsultation(cid);
      setSelectedHistory(data);
    } catch (err) {
      console.error('Failed to fetch consultation details:', err);
    }
  };

  // Run script parser on upload/text change
  const handleParseScript = async (fileToParse?: File, textToParse?: string) => {
    if (!fileToParse && !textToParse) return;
    setIsParsing(true);
    setParseError(null);
    try {
      const result = await api.parseScript(fileToParse, textToParse);
      setParseResult(result);
      if (result.detected_language) {
        const langMap: Record<string, string> = {
          'hi': 'hi_en',
          'mr': 'mr_en',
          'gu': 'gu_en',
          'te': 'te_en'
        };
        const mappedLang = langMap[result.detected_language] || result.detected_language;
        if (['gu', 'te', 'hi_en', 'mr_en', 'gu_en', 'te_en'].includes(mappedLang)) {
          setGlobalLanguage(mappedLang);
        }
      }

      // Seed default settings for newly parsed speakers
      const newSettings: Record<string, SpeakerSettings> = {};
      const langMap: Record<string, string> = {
        'hi': 'hi_en',
        'mr': 'mr_en',
        'gu': 'gu_en',
        'te': 'te_en'
      };
      result.speakers.forEach(speaker => {
        const isElderly = speaker.toLowerCase().includes('elder') || speaker.toLowerCase().includes('old');
        const isFemale = speaker.toLowerCase().includes('nurse') || speaker.toLowerCase().includes('mother') || speaker.toLowerCase().includes('wife') || speaker.toLowerCase().includes('sister');

        newSettings[speaker] = {
          gender: isFemale ? 'female' : 'male',
          age: isElderly ? 'elderly' : 'adult',
          engine: globalEngine,
          language: result.detected_language ? (langMap[result.detected_language] || result.detected_language) : globalLanguage,
        };
      });
      setSpeakerSettings(newSettings);
    } catch (err: any) {
      setParseError(err.message || 'Error occurred while parsing the script.');
      setParseResult(null);
    } finally {
      setIsParsing(false);
    }
  };

  // Handle single consultation submission
  const handleGenerate = async () => {
    if (!parseResult) return;
    setParseError(null);
    try {
      const params = {
        name,
        script: file ? undefined : scriptText,
        file: file || undefined,
        language: globalLanguage,
        engine: globalEngine,
        seed: globalSeed,
        speaker_settings: speakerSettings,
        noise_settings: noiseSettings,
        randomize: !showAdvanced,
      };

      const res = await api.createConsultation(params);
      setActiveJobId(res.id);
      setSubmitSuccess("Consultation queued! Check the History tab for progress.");
      setScriptText('');
      setFile(null);
      setParseResult(null);
      fetchHistory();
      setTimeout(() => setSubmitSuccess(null), 5000);
    } catch (err: any) {
      setParseError(err.message || 'Error starting generator.');
    }
  };

  // Handle batch generation
  const handleBatchGenerate = async () => {
    try {
      const validScripts = batchScripts.filter(s => s.script.trim().length > 0);
      if (validScripts.length === 0) return;

      const params = {
        name: batchName,
        scripts: validScripts.map(s => ({
          name: s.name || `Script - ${s.id}`,
          script: s.script,
          language: globalLanguage
        })),
        engine: globalEngine,
        seed: globalSeed,
        speaker_settings: {}, // fallback defaults
        noise_settings: noiseSettings,
        randomize: !showAdvanced,
      };

      const res = await api.createBatch(params);
      setActiveBatchJobId(res.batch_id);
      setSubmitSuccess("Batch job queued! Check the History tab for progress.");
      setBatchScripts([{ id: '1', name: '', script: '' }]);
      fetchHistory();
      setTimeout(() => setSubmitSuccess(null), 5000);
    } catch (err) {
      console.error('Failed to launch batch job:', err);
    }
  };

  // Handle deletion
  const handleDeleteConsultation = async (cid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this consultation?')) return;
    try {
      await api.deleteConsultation(cid);
      fetchHistory();
      if (selectedHistoryId === cid) {
        setSelectedHistoryId(null);
        setSelectedHistory(null);
      }
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  // Handle Audio Player
  const togglePlayAudio = (url: string, playId: string) => {
    if (currentlyPlayingId === playId) {
      if (audioPlayerRef.current) {
        if (audioPlayerRef.current.paused) {
          audioPlayerRef.current.play();
        } else {
          audioPlayerRef.current.pause();
        }
      }
    } else {
      setPlayingAudioUrl(url);
      setCurrentlyPlayingId(playId);
    }
  };

  // Synchronize play state manually
  useEffect(() => {
    if (!playingAudioUrl) return;
    if (audioPlayerRef.current) {
      audioPlayerRef.current.src = playingAudioUrl;
      audioPlayerRef.current.play().catch(err => console.error('Audio play error:', err));
    }
  }, [playingAudioUrl]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col antialiased">
      {/* Top Banner Header */}
      <header className="bg-slate-900/80 backdrop-blur-md border-b border-slate-800 py-4 px-6 sticky top-0 z-50 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <div className="bg-teal-500/10 p-2.5 rounded-xl border border-teal-500/20 text-teal-400">
            <Volume2 className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-teal-300 via-emerald-400 to-teal-400 bg-clip-text text-transparent">
              Indian OPD Audio Generator
            </h1>
            <p className="text-xs text-slate-400">Realistic doctor-patient voice synthesis for clinical setups</p>
          </div>
        </div>

        {/* Server Status Monitor */}
        <div className="flex items-center gap-4 bg-slate-950/80 px-4 py-2 rounded-xl border border-slate-800 text-xs">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-teal-400" />
            <span className="text-slate-400">Device:</span>
            <span className="font-semibold text-teal-300 uppercase">{health?.device || 'detecting...'}</span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Engines:</span>
            <span className={`px-1.5 py-0.5 rounded font-mono ${health?.engines.parler ? 'bg-teal-950 text-teal-400 border border-teal-800/35' : 'bg-slate-900 text-slate-500'}`}>Parler</span>
            <span className={`px-1.5 py-0.5 rounded font-mono ${health?.engines.indicf5 ? 'bg-teal-950 text-teal-400 border border-teal-800/35' : 'bg-slate-900 text-slate-500'}`}>IndicF5</span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-full ${health?.status === 'ok' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-red-500 animate-ping'}`} />
            <span className="text-slate-400">{health?.status === 'ok' ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </header>

      {/* Main Tabs Navigation */}
      <div className="max-w-7xl w-full mx-auto px-4 md:px-8 py-6 flex-1 flex flex-col gap-6">
        <nav className="flex bg-slate-900 p-1.5 rounded-xl border border-slate-800 w-fit gap-1">
          <button
            onClick={() => setActiveTab('generate')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'generate' ? 'bg-teal-500 text-slate-950 font-semibold shadow-md' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
          >
            <FileText className="w-4 h-4" />
            Generate Audio
          </button>
          <button
            onClick={() => setActiveTab('batch')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'batch' ? 'bg-teal-500 text-slate-950 font-semibold shadow-md' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
          >
            <Layers className="w-4 h-4" />
            Batch Queue
          </button>
          <button
            onClick={() => { setActiveTab('history'); fetchHistory(); }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'history' ? 'bg-teal-500 text-slate-950 font-semibold shadow-md' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
          >
            <History className="w-4 h-4" />
            History Library
          </button>
        </nav>

        {/* Global Hidden Audio Tag for Audio Player */}
        <audio
          ref={audioPlayerRef}
          onEnded={() => setCurrentlyPlayingId(null)}
          onPause={() => setCurrentlyPlayingId(null)}
          onPlay={() => { }}
          className="hidden"
        />

        {/* Generation Tab */}
        {activeTab === 'generate' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left Side Column: Input Form */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-6 shadow-xl flex flex-col gap-5">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200">
                  <FileText className="w-5 h-5 text-teal-400" />
                  OPD Consultation Script
                </h2>

                <div className="flex flex-col gap-2">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Consultation Session Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:border-teal-500/60 transition"
                    placeholder="e.g. Pediatric Fever consultation - Arjun"
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Language</label>
                  <select
                    value={globalLanguage}
                    onChange={e => setGlobalLanguage(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:border-teal-500/60 transition cursor-pointer"
                  >
                    <option value="gu">Gujarati</option>
                    <option value="te">Telugu</option>
                    <option value="hi_en">Hindi + English</option>
                    <option value="mr_en">Marathi + English</option>
                    <option value="gu_en">Gujarati + English</option>
                    <option value="te_en">Telugu + English</option>
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Consultation Script Text</label>
                    <span className="text-xs text-slate-500">Formats: SpeakerName: Speech Text...</span>
                  </div>
                  <textarea
                    value={scriptText}
                    disabled={!!file}
                    onChange={e => {
                      setScriptText(e.target.value);
                      if (e.target.value.trim().length > 10) {
                        handleParseScript(undefined, e.target.value);
                      }
                    }}
                    rows={8}
                    className="bg-slate-950 border border-slate-800 rounded-xl p-4 text-slate-300 font-mono text-sm leading-relaxed focus:outline-none focus:border-teal-500/60 transition disabled:opacity-50"
                    placeholder={`Doctor: Aiye, Arjun ko kya problem hai?\nPatient: Doctor sahab, kal raat se isko tez bukhaar hai.\nDoctor: Temperature check kiya tha?\nPatient: Haan, 102 degree tha subah.`}
                  />
                </div>

                <div className="flex items-center gap-4">
                  <div className="h-px bg-slate-800 flex-1" />
                  <span className="text-xs text-slate-500 font-medium">OR UPLOAD FILE</span>
                  <div className="h-px bg-slate-800 flex-1" />
                </div>

                <div className="flex items-center gap-4">
                  <label className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-slate-800 hover:border-teal-500/40 bg-slate-950/40 hover:bg-slate-950/80 rounded-xl py-6 px-4 cursor-pointer transition text-slate-400 hover:text-slate-200">
                    <Upload className="w-6 h-6 mb-2 text-slate-500" />
                    <span className="text-sm font-medium">{file ? file.name : 'Upload file (.txt, .md, .pdf, .docx, .json)'}</span>
                    <input
                      type="file"
                      accept=".txt,.md,.pdf,.docx,.doc,.json"
                      className="hidden"
                      onChange={e => {
                        const files = e.target.files;
                        if (files && files[0]) {
                          setFile(files[0]);
                          handleParseScript(files[0]);
                        }
                      }}
                    />
                  </label>
                  {file && (
                    <button
                      onClick={() => { setFile(null); setParseResult(null); }}
                      className="p-3 bg-red-950/30 border border-red-900/30 text-red-400 hover:bg-red-900/30 rounded-xl transition"
                      title="Clear uploaded file"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>

                {showAdvanced && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2 animate-fadeIn">
                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Synthesis Engine</label>
                      <select
                        value={globalEngine}
                        onChange={e => setGlobalEngine(e.target.value as any)}
                        className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-slate-300 focus:outline-none focus:border-teal-500/60"
                      >
                        <option value="parler">Indic-Parler-TTS (Fast)</option>
                        <option value="indicf5">IndicF5 (Voice Cloned)</option>
                      </select>
                    </div>

                    <div className="flex flex-col gap-2">
                      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Random Seed</label>
                      <input
                        type="number"
                        value={globalSeed}
                        onChange={e => setGlobalSeed(parseInt(e.target.value) || 0)}
                        className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-slate-300 focus:outline-none focus:border-teal-500/60"
                      />
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between border-t border-slate-800 pt-4 mt-2">
                  <div className="flex flex-col">
                    <span className="text-sm font-semibold text-slate-300">Advanced Controls</span>
                    <span className="text-xs text-slate-500">Manual override for voice casting, seeds, and ambient mix</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showAdvanced}
                      onChange={e => setShowAdvanced(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:bg-slate-950 peer-checked:bg-teal-400" />
                  </label>
                </div>
              </div>

              {/* Background Noise Options Card */}
              {showAdvanced && (
                <div className="bg-slate-900 border border-slate-800/80 rounded-2xl p-6 shadow-xl flex flex-col gap-4">
                  <div className="flex justify-between items-center">
                    <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200">
                      <Volume2 className="w-5 h-5 text-teal-400" />
                      Clinic Ambient Noise
                    </h2>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={noiseSettings.enabled}
                        onChange={e => setNoiseSettings(prev => ({ ...prev, enabled: e.target.checked }))}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-slate-400 after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:bg-slate-950 peer-checked:bg-teal-400" />
                    </label>
                  </div>

                  {noiseSettings.enabled && (
                    <div className="flex flex-col gap-5 mt-2 animate-fadeIn">
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {Object.entries(noiseTypes).map(([typeKey, displayName]) => (
                          <label
                            key={typeKey}
                            className={`flex items-center gap-2.5 p-3 rounded-xl border cursor-pointer text-xs font-medium transition ${noiseSettings.types[typeKey]
                                ? 'bg-teal-950/20 border-teal-500/40 text-teal-300'
                                : 'bg-slate-950 border-slate-800/80 text-slate-400 hover:text-slate-200'
                              }`}
                          >
                            <input
                              type="checkbox"
                              checked={!!noiseSettings.types[typeKey]}
                              onChange={e => setNoiseSettings(prev => ({
                                ...prev,
                                types: { ...prev.types, [typeKey]: e.target.checked }
                              }))}
                              className="hidden"
                            />
                            <span className={`w-3.5 h-3.5 rounded flex items-center justify-center border ${noiseSettings.types[typeKey] ? 'bg-teal-500 border-teal-500 text-slate-950' : 'border-slate-700'
                              }`}>
                              {noiseSettings.types[typeKey] && '✓'}
                            </span>
                            {displayName}
                          </label>
                        ))}
                      </div>

                      <div className="flex flex-col gap-2">
                        <div className="flex justify-between text-xs font-medium text-slate-400">
                          <span>Noise Intensity (Volume)</span>
                          <span className="text-teal-400">{Math.round(noiseSettings.intensity * 100)}%</span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={noiseSettings.intensity}
                          onChange={e => setNoiseSettings(prev => ({ ...prev, intensity: parseFloat(e.target.value) }))}
                          className="w-full accent-teal-400 cursor-pointer bg-slate-950 h-2 rounded-lg"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right Side Column: Config & Generation Status */}
            <div className="lg:col-span-5 flex flex-col gap-6">
              {/* Parse Preview & Speakers */}
              {isParsing && (
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl text-center py-12 flex flex-col items-center justify-center gap-3">
                  <RefreshCw className="w-8 h-8 text-teal-400 animate-spin" />
                  <p className="text-slate-400 text-sm font-medium">Parsing consultation script...</p>
                </div>
              )}

              {parseError && (
                <div className="bg-red-950/20 border border-red-900/30 text-red-300 rounded-2xl p-6 flex gap-3 shadow-xl">
                  <AlertTriangle className="w-6 h-6 text-red-500 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-sm text-red-200">Script Parse Failed</h4>
                    <p className="text-xs text-red-400 leading-relaxed mt-1">{parseError}</p>
                  </div>
                </div>
              )}

              {submitSuccess && (
                <div className="bg-emerald-950/20 border border-emerald-900/30 text-emerald-300 rounded-2xl p-6 flex gap-3 shadow-xl">
                  <Activity className="w-6 h-6 text-emerald-500 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-sm text-emerald-200">Success</h4>
                    <p className="text-xs text-emerald-400 leading-relaxed mt-1">{submitSuccess}</p>
                  </div>
                </div>
              )}

              {!isParsing && parseResult && (
                showAdvanced ? (
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-4 animate-fadeIn">
                    <div className="flex items-center justify-between">
                      <h2 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
                        <User className="w-5 h-5 text-teal-400" />
                        Speaker Voice Mapping
                      </h2>
                      <span className="bg-slate-950 text-slate-400 border border-slate-800 px-2 py-0.5 rounded text-xs font-mono">
                        {parseResult.total_turns} turns
                      </span>
                    </div>

                    <p className="text-xs text-slate-400 leading-relaxed">
                      Adjust gender, age, and voice prompts for each speaker detected in the script.
                    </p>

                    <div className="flex flex-col gap-4 max-h-[360px] overflow-y-auto pr-1">
                      {parseResult.speakers.map(speaker => {
                        const cfg = speakerSettings[speaker] || { gender: 'male', age: 'adult', engine: 'parler' };
                        return (
                          <div key={speaker} className="bg-slate-950 border border-slate-800/80 rounded-xl p-4 flex flex-col gap-3">
                            <div className="flex justify-between items-center">
                              <span className="font-bold text-teal-300 text-sm">{speaker}</span>
                              <span className="text-slate-500 text-xs font-mono">Preset Options</span>
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                              <div className="flex flex-col gap-1">
                                <label className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Gender</label>
                                <select
                                  value={cfg.gender}
                                  onChange={e => setSpeakerSettings(prev => ({
                                    ...prev,
                                    [speaker]: { ...prev[speaker], gender: e.target.value as any }
                                  }))}
                                  className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300"
                                >
                                  <option value="male">Male</option>
                                  <option value="female">Female</option>
                                </select>
                              </div>

                              <div className="flex flex-col gap-1">
                                <label className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Age Bracket</label>
                                <select
                                  value={cfg.age}
                                  onChange={e => setSpeakerSettings(prev => ({
                                    ...prev,
                                    [speaker]: { ...prev[speaker], age: e.target.value as any }
                                  }))}
                                  className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300"
                                >
                                  <option value="adult">Adult</option>
                                  <option value="elderly">Elderly</option>
                                  <option value="young">Young</option>
                                </select>
                              </div>
                            </div>

                            {/* Custom prompt text box */}
                            <div className="flex flex-col gap-1.5">
                              <label className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Voice prompt (Parler description)</label>
                              <textarea
                                value={cfg.voice_description || ''}
                                onChange={e => setSpeakerSettings(prev => ({
                                  ...prev,
                                  [speaker]: { ...prev[speaker], voice_description: e.target.value }
                                }))}
                                rows={2}
                                className="bg-slate-900 border border-slate-800 rounded-lg p-2 text-xs text-slate-300 font-mono focus:outline-none"
                                placeholder="Describe custom features (accent, emotion, tempo)..."
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <button
                      onClick={handleGenerate}
                      disabled={!!activeJobId}
                      className="bg-gradient-to-r from-teal-400 to-emerald-500 hover:from-teal-300 hover:to-emerald-400 text-slate-950 font-bold py-3.5 px-6 rounded-xl transition text-center flex items-center justify-center gap-2 shadow-lg shadow-teal-500/10 cursor-pointer disabled:opacity-50"
                    >
                      <Volume2 className="w-5 h-5" />
                      GENERATE CONSULTATION AUDIO
                    </button>
                  </div>
                ) : (
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-5 animate-fadeIn">
                    <div className="flex items-center justify-between">
                      <h2 className="text-lg font-semibold text-slate-200 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-teal-400" />
                        Session Summary
                      </h2>
                      <span className="bg-slate-950 text-slate-400 border border-slate-800 px-2 py-0.5 rounded text-xs font-mono">
                        {parseResult.total_turns} turns
                      </span>
                    </div>

                    <div className="text-sm text-slate-300 flex flex-col gap-3 bg-slate-950/60 p-4 rounded-xl border border-slate-850">
                      <div>
                        <span className="text-slate-400 font-medium">Speakers:</span>{' '}
                        <span className="font-bold text-teal-300">{parseResult.speakers.join(', ')}</span>
                      </div>
                      <div>
                        <span className="text-slate-400 font-medium">Casting & Style:</span>{' '}
                        <span className="text-slate-200">Automatic & Randomized on each generation</span>
                      </div>
                      <div>
                        <span className="text-slate-400 font-medium">Ambient Noise:</span>{' '}
                        <span className="text-slate-200">Clinic mix (random types and intensity)</span>
                      </div>
                    </div>

                    <button
                      onClick={handleGenerate}
                      disabled={!!activeJobId}
                      className="bg-gradient-to-r from-teal-400 to-emerald-500 hover:from-teal-300 hover:to-emerald-400 text-slate-950 font-bold py-3.5 px-6 rounded-xl transition text-center flex items-center justify-center gap-2 shadow-lg shadow-teal-500/10 cursor-pointer disabled:opacity-50"
                    >
                      <Volume2 className="w-5 h-5" />
                      GENERATE CONSULTATION AUDIO
                    </button>
                  </div>
                )
              )}

              {!isParsing && !parseResult && !jobProgress && (
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl text-center py-20 flex flex-col items-center justify-center gap-3 text-slate-500 animate-fadeIn">
                  <FileText className="w-12 h-12 text-slate-700" />
                  <p className="text-sm">Upload or paste a script on the left to review details and generate audio.</p>
                </div>
              )}

              {/* Job Progress Indicator */}
              {jobProgress && (
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-4 animate-fadeIn">
                  <div className="flex justify-between items-center">
                    <h3 className="font-semibold text-slate-200 flex items-center gap-2">
                      <RefreshCw className={`w-4 h-4 text-teal-400 ${activeJobId ? 'animate-spin' : ''}`} />
                      Audio Synthesis Progress
                    </h3>
                    <span className="text-xs bg-teal-950 text-teal-400 px-2 py-0.5 rounded border border-teal-800/30 uppercase font-bold font-mono">
                      {jobProgress.status}
                    </span>
                  </div>

                  <div className="w-full bg-slate-950 rounded-full h-3 overflow-hidden border border-slate-800">
                    <div
                      className="bg-gradient-to-r from-teal-400 to-emerald-400 h-full rounded-full transition-all duration-500"
                      style={{ width: `${jobProgress.percent}%` }}
                    />
                  </div>

                  {activeJobId && getRemainingTimeText() && (
                    <div className="text-right text-xs text-teal-400 font-medium">
                      {getRemainingTimeText()}
                    </div>
                  )}

                  <div className="grid grid-cols-4 gap-2 text-center text-xs">
                    <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800/60">
                      <div className="text-slate-500 mb-0.5 uppercase tracking-wide font-semibold text-[9px]">Total</div>
                      <div className="font-bold text-slate-200">{jobProgress.total}</div>
                    </div>
                    <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800/60">
                      <div className="text-emerald-500 mb-0.5 uppercase tracking-wide font-semibold text-[9px]">Done</div>
                      <div className="font-bold text-emerald-400">{jobProgress.done}</div>
                    </div>
                    <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800/60">
                      <div className="text-amber-500 mb-0.5 uppercase tracking-wide font-semibold text-[9px]">Processing</div>
                      <div className="font-bold text-amber-400">{jobProgress.processing}</div>
                    </div>
                    <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800/60">
                      <div className="text-red-500 mb-0.5 uppercase tracking-wide font-semibold text-[9px]">Error</div>
                      <div className="font-bold text-red-400">{jobProgress.error}</div>
                    </div>
                  </div>

                  {activeJobId && (
                    <p className="text-slate-400 text-xs text-center leading-relaxed">
                      Synthesis is running in background. You can navigate away or refresh; the generator will resume automatically.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Batch Queue Tab */}
        {activeTab === 'batch' && (
          <div className="max-w-4xl w-full mx-auto flex flex-col gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-5">
              <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200">
                <Layers className="w-5 h-5 text-teal-400" />
                Batch Generation Mode
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Add multiple scripts to build a batch queue. All scripts will be synthesised sequentially using standard defaults. Once finished, download everything in a single mixed ZIP file.
              </p>

              <div className="flex flex-col gap-2">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Batch Name</label>
                <input
                  type="text"
                  value={batchName}
                  onChange={e => setBatchName(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 focus:outline-none"
                  placeholder="e.g. Wednesday OPD Scripts"
                />
              </div>

              {/* Scripts List */}
              <div className="flex flex-col gap-4">
                {batchScripts.map((item, index) => (
                  <div key={item.id} className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-3 relative">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold text-teal-400 uppercase">Consultation script #{index + 1}</span>
                      {batchScripts.length > 1 && (
                        <button
                          onClick={() => setBatchScripts(prev => prev.filter(x => x.id !== item.id))}
                          className="text-slate-500 hover:text-red-400 p-1"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className="md:col-span-1 flex flex-col gap-2">
                        <label className="text-[10px] uppercase font-bold text-slate-500">Name</label>
                        <input
                          type="text"
                          value={item.name}
                          onChange={e => {
                            const updated = [...batchScripts];
                            updated[index].name = e.target.value;
                            setBatchScripts(updated);
                          }}
                          className="bg-slate-900 border border-slate-850 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none"
                          placeholder="Script name"
                        />
                      </div>
                      <div className="md:col-span-3 flex flex-col gap-2">
                        <label className="text-[10px] uppercase font-bold text-slate-500">Script Body</label>
                        <textarea
                          value={item.script}
                          onChange={e => {
                            const updated = [...batchScripts];
                            updated[index].script = e.target.value;
                            setBatchScripts(updated);
                          }}
                          rows={3}
                          className="bg-slate-900 border border-slate-850 rounded-lg p-3 text-xs text-slate-200 focus:outline-none font-mono"
                          placeholder="Doctor: Aiye...&#10;Patient: ..."
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-between items-center mt-2">
                <button
                  onClick={() => setBatchScripts(prev => [...prev, { id: Date.now().toString(), name: `Script ${prev.length + 1}`, script: '' }])}
                  className="bg-slate-950 hover:bg-slate-850 border border-slate-800 text-teal-400 font-semibold px-4 py-2 rounded-xl transition text-xs flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  Add another script
                </button>

                <button
                  onClick={handleBatchGenerate}
                  disabled={!!activeBatchJobId}
                  className="bg-gradient-to-r from-teal-400 to-emerald-500 hover:from-teal-300 hover:to-emerald-400 text-slate-950 font-bold px-6 py-2.5 rounded-xl transition text-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  <Layers className="w-4 h-4" />
                  QUEUE BATCH GENERATION
                </button>
              </div>
            </div>

            {/* Active Batch Progress Monitor */}
            {batchJobProgress && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-4 animate-fadeIn">
                <div className="flex justify-between items-center">
                  <h3 className="font-semibold text-slate-200 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-teal-400 animate-pulse" />
                    Active Batch Process Status
                  </h3>
                  <span className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800/40 px-2 py-0.5 rounded font-bold font-mono">
                    {batchJobProgress.status}
                  </span>
                </div>

                <div className="flex flex-col gap-3">
                  {batchJobProgress.consultations.map((c: any, index: number) => (
                    <div key={c.id} className="bg-slate-950 border border-slate-850 p-3.5 rounded-xl flex items-center justify-between text-xs">
                      <div className="flex items-center gap-3">
                        <span className="text-slate-500 font-mono">#{index + 1}</span>
                        <span className="font-semibold text-slate-300">{c.name}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold font-mono ${c.status === 'done' ? 'bg-emerald-950 text-emerald-400' :
                            c.status === 'processing' ? 'bg-amber-950 text-amber-400 animate-pulse' :
                              c.status === 'error' ? 'bg-red-950 text-red-400' : 'bg-slate-900 text-slate-500'
                          }`}>
                          {c.status}
                        </span>
                        {c.status === 'done' && (
                          <a
                            href={`/api/consultations/${c.id}/audio/full?download=true`}
                            className="bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800 p-1.5 rounded transition"
                            title="Download Audio (MP3)"
                            download
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Download className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {activeBatchJobId && (
                  <p className="text-slate-500 text-xs text-center">
                    Queue is executing in order. You will see individual ZIPs or download the entire batch ZIP from history once done.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left Side: History List */}
            <div className="lg:col-span-5 flex flex-col gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-lg font-semibold flex items-center gap-2 text-slate-200">
                    <History className="w-5 h-5 text-teal-400" />
                    Consultation Library
                  </h2>
                  <button
                    onClick={fetchHistory}
                    className="p-1.5 bg-slate-950 hover:bg-slate-850 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 transition"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </div>

                {loadingHistory && history.length === 0 && (
                  <div className="py-12 text-center text-slate-500 text-sm">
                    Loading consultations...
                  </div>
                )}

                {!loadingHistory && history.length === 0 && (
                  <div className="py-12 text-center text-slate-500 text-sm flex flex-col items-center gap-2">
                    <FileText className="w-8 h-8 text-slate-700" />
                    No consultations generated yet.
                  </div>
                )}

                <div className="flex flex-col gap-3 max-h-[500px] overflow-y-auto pr-1">
                  {history.map(item => {
                    const isSelected = selectedHistoryId === item.id;
                    const dateStr = new Date(item.created_at).toLocaleString();
                    return (
                      <div
                        key={item.id}
                        onClick={() => {
                          setSelectedHistoryId(item.id);
                          fetchConsultationDetail(item.id);
                        }}
                        className={`border rounded-xl p-4 cursor-pointer transition flex flex-col gap-2 relative group ${isSelected
                            ? 'bg-teal-950/20 border-teal-500/40 text-teal-300'
                            : 'bg-slate-950 border-slate-850/80 hover:bg-slate-900/60 text-slate-300'
                          }`}
                      >
                        <div className="flex justify-between items-start gap-4">
                          <span className="font-semibold text-sm leading-tight">{item.name}</span>
                          <span className={`px-2 py-0.5 rounded text-[9px] uppercase font-bold font-mono ${item.status === 'done' ? 'bg-emerald-950 text-emerald-400 border border-emerald-900/30' :
                              item.status === 'processing' ? 'bg-amber-950 text-amber-400 border border-amber-900/30 animate-pulse' :
                                item.status === 'error' ? 'bg-red-950 text-red-400 border border-red-900/30' : 'bg-slate-900 text-slate-500'
                            }`}>
                            {item.status}
                          </span>
                        </div>

                        <div className="flex justify-between items-center text-[10px] text-slate-500 mt-1">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {dateStr}
                          </span>
                          <span className="bg-slate-900 border border-slate-800 px-1.5 py-0.5 rounded text-slate-400 font-mono">
                            {item.completed_utterances}/{item.total_utterances} turns
                          </span>
                          {(item.status === 'processing' || item.status === 'queued') && (
                            <span className="text-[10px] text-amber-500 ml-2 animate-pulse">
                              ~{Math.ceil((item.total_utterances - item.completed_utterances) * (item.engine === 'indicf5' ? 40 : 15) / 60)}m left
                            </span>
                          )}
                        </div>

                        <button
                          onClick={(e) => handleDeleteConsultation(item.id, e)}
                          className="absolute right-3 top-3 opacity-0 group-hover:opacity-150 p-1.5 text-slate-500 hover:text-red-400 transition bg-slate-900/50 hover:bg-slate-900 rounded-lg border border-slate-800/40"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                {history.some(c => c.status === 'done') && (
                  <a
                    href={`/api/download-all`}
                    className="bg-slate-950 hover:bg-slate-850 border border-slate-800 hover:border-teal-500/20 text-slate-300 hover:text-slate-100 font-semibold py-3 px-4 rounded-xl transition text-xs flex items-center justify-center gap-1.5 mt-2"
                  >
                    <FolderArchive className="w-4 h-4 text-teal-400" />
                    DOWNLOAD ALL COMPLETED (ZIP)
                  </a>
                )}
              </div>
            </div>

            {/* Right Side: History Detail View */}
            <div className="lg:col-span-7 flex flex-col gap-6">
              {!selectedHistory && (
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl text-center py-20 flex flex-col items-center justify-center gap-3 text-slate-500">
                  <History className="w-12 h-12 text-slate-700" />
                  <p className="text-sm">Select a consultation from the library to view files and audio.</p>
                </div>
              )}

              {selectedHistory && (
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-5 animate-fadeIn">
                  <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
                    <div>
                      <h2 className="text-lg font-bold text-slate-200">{selectedHistory.name}</h2>
                      <p className="text-xs text-slate-500 mt-1">
                        Generated via <span className="font-mono text-slate-400">{selectedHistory.engine}</span> | Language: <span className="font-mono text-slate-400">{selectedHistory.language}</span> | Seed: <span className="font-mono text-slate-400">{selectedHistory.seed}</span>
                      </p>
                    </div>

                    <div className="flex gap-2">
                      <a
                        href={`/api/consultations/${selectedHistory.id}/audio/full?download=true`}
                        className="bg-gradient-to-r from-teal-400 to-emerald-500 hover:from-teal-300 hover:to-emerald-400 text-slate-950 font-bold px-4 py-2 rounded-xl transition text-xs flex items-center gap-1.5 shadow-md animate-pulseHover"
                        download
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Download className="w-4 h-4" />
                        Download Audio (MP3)
                      </a>
                      <a
                        href={`/api/consultations/${selectedHistory.id}/download`}
                        className="bg-slate-950 hover:bg-slate-850 border border-slate-800 text-slate-400 hover:text-slate-200 font-semibold px-3 py-2 rounded-xl transition text-xs flex items-center gap-1.5 shadow-md"
                        title="Download ZIP archive with individual turns"
                      >
                        <FolderArchive className="w-3.5 h-3.5" />
                        ZIP
                      </a>
                    </div>
                  </div>

                  {/* Full Audio Player */}
                  {selectedHistory.status === 'done' && (
                    <div className="bg-slate-950/80 border border-slate-800 p-4 rounded-2xl flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3.5">
                        <button
                          onClick={() => togglePlayAudio(`/api/consultations/${selectedHistory.id}/audio/full`, selectedHistory.id + 'full')}
                          className="bg-teal-500 text-slate-950 p-3.5 rounded-full hover:scale-105 active:scale-95 transition shadow-lg shadow-teal-500/20"
                        >
                          {currentlyPlayingId === selectedHistory.id + 'full' ? (
                            <Pause className="w-5 h-5 fill-current" />
                          ) : (
                            <Play className="w-5 h-5 fill-current" />
                          )}
                        </button>
                        <div>
                          <h4 className="font-semibold text-sm text-slate-200">Full Audio OPD Consultation</h4>
                          <p className="text-xs text-slate-500">Concatenated speech turns with clinic noise layered</p>
                        </div>
                      </div>
                      <a
                        href={`/api/consultations/${selectedHistory.id}/audio/full?download=true`}
                        className="p-2.5 bg-slate-900 border border-slate-800 hover:text-slate-100 rounded-xl text-slate-400 transition"
                        title="Download Full MP3"
                        download
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Download className="w-4 h-4" />
                      </a>
                    </div>
                  )}

                  {selectedHistory.error_message && (
                    <div className="bg-red-950/20 border border-red-900/30 text-red-300 rounded-xl p-4 flex gap-3">
                      <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
                      <div className="text-xs">
                        <span className="font-bold">Error Info:</span> {selectedHistory.error_message}
                      </div>
                    </div>
                  )}

                  {/* Utterance turns list */}
                  <div className="flex flex-col gap-3">
                    <h3 className="font-semibold text-sm text-slate-400">Speech Conversation Script</h3>

                    <div className="flex flex-col gap-3 max-h-[380px] overflow-y-auto pr-1">
                      {selectedHistory.utterances?.map((utt) => {
                        const isDoc = utt.speaker.toLowerCase().includes('doc') || utt.speaker.toLowerCase().includes('dr');
                        const isPatient = utt.speaker.toLowerCase().includes('patient') || utt.speaker.toLowerCase().includes('pt');

                        return (
                          <div
                            key={utt.id}
                            className={`border border-slate-800/60 p-3.5 rounded-xl flex flex-col gap-2 transition ${isDoc ? 'bg-teal-950/5 border-l-4 border-l-teal-500' :
                                isPatient ? 'bg-emerald-950/5 border-l-4 border-l-emerald-500' : 'bg-slate-950/40 border-l-4 border-l-slate-700'
                              }`}
                          >
                            <div className="flex justify-between items-center gap-4">
                              <span className={`font-bold text-xs uppercase ${isDoc ? 'text-teal-400' :
                                  isPatient ? 'text-emerald-400' : 'text-slate-400'
                                }`}>
                                {utt.speaker}
                              </span>

                              <div className="flex items-center gap-2">
                                <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold font-mono uppercase ${utt.status === 'done' ? 'bg-emerald-950 text-emerald-400' :
                                    utt.status === 'processing' ? 'bg-amber-950 text-amber-400 animate-pulse' : 'bg-slate-900 text-slate-500'
                                  }`}>
                                  {utt.status}
                                </span>

                                {utt.status === 'done' && (
                                  <>
                                    <button
                                      onClick={() => togglePlayAudio(`/api/consultations/${selectedHistory.id}/utterances/${utt.id}/audio`, utt.id)}
                                      className="p-1.5 bg-slate-900 border border-slate-800 hover:border-teal-500/20 text-slate-400 hover:text-slate-200 rounded-lg transition"
                                      title="Play Audio"
                                    >
                                      {currentlyPlayingId === utt.id ? (
                                        <Pause className="w-3.5 h-3.5 text-teal-400" />
                                      ) : (
                                        <Play className="w-3.5 h-3.5" />
                                      )}
                                    </button>
                                    <a
                                      href={`/api/consultations/${selectedHistory.id}/utterances/${utt.id}/audio?download=true`}
                                      className="p-1.5 bg-slate-900 border border-slate-800 hover:border-teal-500/20 text-slate-400 hover:text-slate-200 rounded-lg transition inline-flex"
                                      title="Download Utterance (MP3)"
                                      download
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <Download className="w-3.5 h-3.5" />
                                    </a>
                                  </>
                                )}
                              </div>
                            </div>

                            <p className="text-sm text-slate-300 leading-relaxed font-mono select-all">{utt.text}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer bar */}
      <footer className="bg-slate-900 border-t border-slate-800 py-4 px-6 text-center text-xs text-slate-500 mt-auto">
        <p>© 2026 Indian OPD Consultation Audio Generator. Local execution using Metal Acceleration (MPS).</p>
      </footer>
    </div>
  );
}
