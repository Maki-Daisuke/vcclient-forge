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
    preview_description: 'Appearance preview. Voice conversion and settings changes are not connected yet.',
    preview_dialog: 'Sample values are shown. Changes and audio operations are not available yet.',
    sample_model: 'Sample RVC model',
    sample_description: 'Sample data for checking the interface. No installed models or devices are loaded.',
    model_management: 'Manage models',
    language: 'Language', theme: 'Toggle color theme', close: 'Close',
    idle: 'Stopped',
    host: 'Audio host', sample_rate: 'Sample rate',
    about: 'About',
    log_empty: 'There are no logs in this appearance preview.',
    licenses: 'Translations and placeholder icons: w-okada/voice-changer. See frontend/NOTICE.md.',
  },
  ja: {
    preview: 'UI プレビュー',
    preview_description: '見た目のプレビューです。音声変換や設定変更は、これから使えるようになります。',
    preview_dialog: '表示はサンプルです。設定の変更や音声の操作は、まだ利用できません。',
    sample_model: 'サンプル RVC モデル',
    sample_description: '画面確認用のサンプルです。実際のモデルやデバイスは読み込んでいません。',
    model_management: 'モデル管理',
    language: '表示言語', theme: '配色を切り替える', close: '閉じる',
    idle: '停止中',
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
