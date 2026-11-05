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
    preview_description: 'Model information is read-only. Audio controls and settings are still an appearance preview.',
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
    preview_description: 'モデル情報を読み取り専用で表示します。音声操作や設定は、まだ見た目のプレビューです。',
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
