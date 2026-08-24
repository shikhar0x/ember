import { writable } from 'svelte/store';

export interface ActiveTrack {
  title: string;
  artist: string;
  coverUrl: string;
  audioUrl: string;
  isLocal: boolean;
  rawTrack?: any;
}

export const activeTrack = writable<ActiveTrack | null>(null);
