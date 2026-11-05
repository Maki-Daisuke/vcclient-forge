import { getContext, setContext } from 'svelte';
import { createInstance, type TOptions } from 'i18next';
import type { ResourceLanguage } from 'i18next';

const dictionaries = import.meta.glob<ResourceLanguage>(
  '../../../web_front/ui/2.1.4/assets/i18n/*/translation.json',
  { eager: true, import: 'default' },
);

export const languages = [
  ['en', 'English'], ['ja', '日本語'], ['ko', '한국어'], ['de', 'Deutsch'],
  ['ar', 'العربية'], ['el', 'Ελληνικά'], ['es', 'Español'], ['fr', 'Français'],
  ['it', 'Italiano'], ['la', 'Latina'], ['ms', 'Bahasa Melayu'],
  ['ru', 'Русский'], ['zh', '中文'],
] as const;

const previewMessages = {
  en: {
    preview: 'UI Preview',
    preview_description: 'Current models and settings are read-only. Audio operations and settings changes are not connected yet.',
    settings_readonly: 'Current settings are read-only. Unavailable values are shown as —. Changes are not connected yet.',
    settings_loading: 'Loading current settings…',
    settings_unavailable: 'Settings could not be loaded. Use Reload above to try again.',
    device_loading: 'Device #{{id}} (loading list…)',
    device_error: 'Device #{{id}} (list unavailable; use Reload to retry)',
    device_missing: 'Device #{{id}} (not in device list)',
    gpu_id: 'GPU #{{id}}',
    input_device_rate: 'Input device sample rate',
    output_device_rate: 'Output device sample rate',
    monitor_device_rate: 'Monitor device sample rate',
    high_pass_cutoff: 'High-pass cutoff', low_pass_cutoff: 'Low-pass cutoff',
    noise_gate_threshold: 'Noise gate threshold',
    io_analysis_interval: 'Input/output analysis interval',
    process_analysis_interval: 'Voice processing analysis interval',
    browser_settings_unavailable: 'Browser-only settings are not available in this view yet.',
    preview_dialog: 'Sample values are shown. Changes and audio operations are not available yet.',
    models_readonly: 'Model information is read-only. Selecting, editing, and saving models are not available yet.',
    models_loading: 'Loading model information…',
    models_empty: 'No models are stored.',
    models_count: '{{count}} stored slots',
    reload_models: 'Reload',
    catalog_error_network: 'Cannot connect to the backend. Start it and reload the model information.',
    catalog_error_http: 'Could not load model information (HTTP {{status}}). Please reload.',
    catalog_error_invalid_response: 'The backend returned an unexpected response. Model information cannot be displayed.',
    catalog_error_timeout: 'The backend did not respond in time. Please reload.',
    current_model_unavailable: 'The configured model (slot {{slot}}) is not in the model list.',
    model_status_pending: 'Downloading',
    model_status_broken: 'Unreadable model',
    model_status_unsupported: 'Unsupported model',
    sample_models_preview: 'Sample model downloads are not connected yet.',
    controls_preview: 'Audio preview',
    not_connected: 'Not connected yet',
    model_management: 'Manage models',
    language: 'Language', theme: 'Toggle color theme', close: 'Close',
    host: 'Audio host', sample_rate: 'Sample rate',
    about: 'About',
    log_empty: 'There are no logs in this appearance preview.',
    licenses: 'Translations and placeholder icons: w-okada/voice-changer. See frontend/NOTICE.md.',
  },
  ja: {
    preview: 'UI プレビュー',
    preview_description: '現在のモデル情報と設定を読み取り専用で表示しています。音声操作や設定変更は、まだ接続していません。',
    settings_readonly: '現在の設定を読み取り専用で表示しています。取得できない値は「—」で示しています。変更機能は、まだ接続していません。',
    settings_loading: '現在の設定を読み込んでいます……',
    settings_unavailable: '設定を読み込めませんでした。上の「再読み込み」からやり直せます。',
    device_loading: 'デバイス #{{id}}（一覧を読み込み中……）',
    device_error: 'デバイス #{{id}}（一覧を取得できません。「再読み込み」で再試行）',
    device_missing: 'デバイス #{{id}}（一覧にありません）',
    gpu_id: 'GPU #{{id}}',
    input_device_rate: '入力デバイスのサンプルレート',
    output_device_rate: '出力デバイスのサンプルレート',
    monitor_device_rate: 'モニターデバイスのサンプルレート',
    high_pass_cutoff: 'ハイパスのカットオフ', low_pass_cutoff: 'ローパスのカットオフ',
    noise_gate_threshold: 'ノイズゲートのしきい値',
    io_analysis_interval: '入出力解析の送信間隔',
    process_analysis_interval: '音声処理解析の送信間隔',
    browser_settings_unavailable: 'ブラウザ側だけで管理する項目は、まだ表示に対応していません。',
    preview_dialog: '表示はサンプルです。設定の変更や音声の操作は、まだ利用できません。',
    models_readonly: 'モデル情報は読み取り専用です。モデルの切り替え・編集・保存は、まだ利用できません。',
    models_loading: 'モデル情報を読み込んでいます……',
    models_empty: '保存されているモデルはありません。',
    models_count: '保存済み {{count}} 枠',
    reload_models: '再読み込み',
    catalog_error_network: 'バックエンドに接続できません。起動を確認して、再読み込みしてください。',
    catalog_error_http: 'モデル情報を取得できませんでした（HTTP {{status}}）。再読み込みしてください。',
    catalog_error_invalid_response: 'バックエンドの応答形式が想定と異なるため、モデル情報を表示できません。',
    catalog_error_timeout: 'バックエンドの応答が間に合いませんでした。再読み込みしてください。',
    current_model_unavailable: '設定されているモデル（スロット {{slot}}）が一覧にありません。',
    model_status_pending: 'ダウンロード中',
    model_status_broken: '読み込めないモデル',
    model_status_unsupported: '未対応のモデル',
    sample_models_preview: 'サンプルモデルのダウンロードは、まだ接続していません。',
    controls_preview: '音声操作プレビュー',
    not_connected: '未接続',
    model_management: 'モデル管理',
    language: '表示言語', theme: '配色を切り替える', close: '閉じる',
    host: 'オーディオホスト', sample_rate: 'サンプルレート',
    about: 'このアプリについて',
    log_empty: '見た目のプレビューのため、ログはありません。',
    licenses: '翻訳・プレースホルダー画像：w-okada/voice-changer。詳細は frontend/NOTICE.md を参照してください。',
  },
};

const contextKey = Symbol('ui');

export class UiState {
  language = $state('ja');
  theme = $state<'light' | 'dark'>('light');
  private i18n = createInstance();

  constructor() {
    const resources = Object.fromEntries(Object.entries(dictionaries).map(([path, dictionary]) => {
      const language = path.split('/').at(-2)!;
      return [language, { translation: {
        ...dictionary,
        forge: previewMessages[language as keyof typeof previewMessages] ?? previewMessages.en,
      } }];
    }));
    // Bundled resources initialize synchronously, with no HTTP backend or detector.
    void this.i18n.init({ resources, lng: 'ja', fallbackLng: 'en', interpolation: { escapeValue: false } });
  }

  t(key: string, options: TOptions = {}): string {
    return this.i18n.t(key, { ...options, lng: this.language }) as string;
  }
}

export function provideUi() {
  return setContext(contextKey, new UiState());
}

export function useUi(): UiState {
  return getContext(contextKey);
}
