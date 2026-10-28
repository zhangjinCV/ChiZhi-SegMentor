import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type {
  EditorBox,
  EditorImage,
  SegmentResult,
  Tool,
  ViewMode,
} from "../types";
import { DEFAULT_POSTPROCESS, type PostprocessOptions } from "../api/client";

export const BOX_COLORS = ["#f59e0b", "#22d3ee", "#a78bfa", "#fb7185", "#34d399", "#60a5fa"];

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cloneBoxes(boxes: EditorBox[]): EditorBox[] {
  return boxes.map((box) => ({ ...box }));
}

interface HistoryEntry {
  imageId: string;
  boxes: EditorBox[];
}

interface EditorState {
  images: EditorImage[];
  currentId: string | null;
  boxesByImage: Record<string, EditorBox[]>;
  resultsByImage: Record<string, Record<string, SegmentResult>>;
  selectedBoxId: string | null;
  threshold: number;
  padding: number;
  postprocess: PostprocessOptions;
  showMask: boolean;
  maskOpacity: number;
  viewMode: ViewMode;
  tool: Tool;
  autoRun: boolean;
  busy: boolean;
  error: string | null;
  past: HistoryEntry[];
  future: HistoryEntry[];

  addPaths(paths: string[]): void;
  addImage(image: EditorImage): void;
  updateImage(id: string, patch: Partial<EditorImage>): void;
  removeImage(id: string): void;
  setCurrent(id: string): void;
  currentImage(): EditorImage | undefined;
  currentBoxes(): EditorBox[];
  currentResults(): Record<string, SegmentResult>;

  addBox(box: EditorBox): void;
  updateBox(id: string, patch: Partial<EditorBox>): void;
  updateBoxMeta(id: string, patch: Partial<EditorBox>): void;
  removeBox(id: string): void;
  selectBox(id: string | null): void;
  boxColor(index: number): string;
  undo(): void;
  redo(): void;

  setResult(boxId: string, result: SegmentResult): void;
  setResultForImage(imageId: string, boxId: string, result: SegmentResult): void;
  removeResult(boxId: string): void;
  setThreshold(value: number): void;
  setPadding(value: number): void;
  setPostprocess(patch: Partial<PostprocessOptions>): void;
  setShowMask(value: boolean): void;
  setMaskOpacity(value: number): void;
  setViewMode(value: ViewMode): void;
  setTool(value: Tool): void;
  setAutoRun(value: boolean): void;
  setBusy(value: boolean): void;
  setError(value: string | null): void;
}

type PersistedState = Pick<
  EditorState,
  | "images"
  | "currentId"
  | "boxesByImage"
  | "selectedBoxId"
  | "threshold"
  | "padding"
  | "postprocess"
  | "showMask"
  | "maskOpacity"
  | "viewMode"
  | "autoRun"
  | "tool"
>;

export const useEditor = create<EditorState>()(
  persist(
    (set, get) => ({
      images: [],
      currentId: null,
      boxesByImage: {},
      resultsByImage: {},
      selectedBoxId: null,
      threshold: 0.5,
      padding: 0,
      postprocess: { ...DEFAULT_POSTPROCESS },
      showMask: true,
      maskOpacity: 0.55,
      viewMode: "overlay",
      tool: "draw",
      autoRun: true,
      busy: false,
      error: null,
      past: [],
      future: [],

      addPaths(paths) {
        const existing = new Set(get().images.map((image) => image.path));
        const images = paths
          .filter((path) => path && !existing.has(path))
          .map((path) => {
            const name = path.split(/[\\/]/).pop() ?? path;
            return {
              id: newId(),
              path,
              name,
              status: "loading" as const,
            };
          });
        if (!images.length) return;
        set((state) => ({
          images: [...state.images, ...images],
          currentId: state.currentId ?? images[0].id,
        }));
      },

      addImage(image) {
        set((state) => ({
          images: [...state.images, image],
          currentId: state.currentId ?? image.id,
        }));
      },

      updateImage(id, patch) {
        set((state) => ({
          images: state.images.map((image) => (image.id === id ? { ...image, ...patch } : image)),
        }));
      },

      removeImage(id) {
        set((state) => {
          const index = state.images.findIndex((image) => image.id === id);
          const images = state.images.filter((image) => image.id !== id);
          const boxesByImage = { ...state.boxesByImage };
          const resultsByImage = { ...state.resultsByImage };
          delete boxesByImage[id];
          delete resultsByImage[id];
          let currentId = state.currentId;
          if (currentId === id) {
            currentId = images[Math.min(index, images.length - 1)]?.id ?? null;
          }
          return {
            images,
            boxesByImage,
            resultsByImage,
            currentId,
            selectedBoxId: null,
            past: state.past.filter((entry) => entry.imageId !== id),
            future: state.future.filter((entry) => entry.imageId !== id),
          };
        });
      },

      setCurrent(id) {
        set({ currentId: id, selectedBoxId: null });
      },

      currentImage() {
        const state = get();
        return state.images.find((image) => image.id === state.currentId);
      },

      currentBoxes() {
        const state = get();
        return state.currentId ? state.boxesByImage[state.currentId] ?? [] : [];
      },

      currentResults() {
        const state = get();
        return state.currentId ? state.resultsByImage[state.currentId] ?? {} : {};
      },

      addBox(box) {
        const state = get();
        if (!state.currentId) return;
        const previous = state.boxesByImage[state.currentId] ?? [];
        set({
          past: [
            ...state.past.slice(-49),
            { imageId: state.currentId, boxes: cloneBoxes(previous) },
          ],
          future: [],
          boxesByImage: {
            ...state.boxesByImage,
            [state.currentId]: [...previous, box],
          },
          selectedBoxId: box.id,
        });
      },

      updateBox(id, patch) {
        const state = get();
        if (!state.currentId) return;
        const previous = state.boxesByImage[state.currentId] ?? [];
        const boxes = previous.map((box) => (box.id === id ? { ...box, ...patch } : box));
        const results = { ...(state.resultsByImage[state.currentId] ?? {}) };
        delete results[id];
        set({
          past: [
            ...state.past.slice(-49),
            { imageId: state.currentId, boxes: cloneBoxes(previous) },
          ],
          future: [],
          boxesByImage: { ...state.boxesByImage, [state.currentId]: boxes },
          resultsByImage: { ...state.resultsByImage, [state.currentId]: results },
        });
      },

      updateBoxMeta(id, patch) {
        const state = get();
        if (!state.currentId) return;
        const previous = state.boxesByImage[state.currentId] ?? [];
        const boxes = previous.map((box) => (box.id === id ? { ...box, ...patch } : box));
        set({
          past: [
            ...state.past.slice(-49),
            { imageId: state.currentId, boxes: cloneBoxes(previous) },
          ],
          future: [],
          boxesByImage: { ...state.boxesByImage, [state.currentId]: boxes },
        });
      },

      removeBox(id) {
        const state = get();
        if (!state.currentId) return;
        const previous = state.boxesByImage[state.currentId] ?? [];
        const boxes = previous.filter((box) => box.id !== id);
        const results = { ...(state.resultsByImage[state.currentId] ?? {}) };
        delete results[id];
        set({
          past: [
            ...state.past.slice(-49),
            { imageId: state.currentId, boxes: cloneBoxes(previous) },
          ],
          future: [],
          boxesByImage: { ...state.boxesByImage, [state.currentId]: boxes },
          resultsByImage: { ...state.resultsByImage, [state.currentId]: results },
          selectedBoxId:
            state.selectedBoxId === id ? boxes[boxes.length - 1]?.id ?? null : state.selectedBoxId,
        });
      },

      selectBox(id) {
        set({ selectedBoxId: id });
      },

      boxColor(index) {
        return BOX_COLORS[index % BOX_COLORS.length];
      },

      undo() {
        const state = get();
        const entry = state.past[state.past.length - 1];
        if (!entry) return;
        const currentBoxes = state.boxesByImage[entry.imageId] ?? [];
        set({
          past: state.past.slice(0, -1),
          future: [
            ...state.future,
            { imageId: entry.imageId, boxes: cloneBoxes(currentBoxes) },
          ],
          boxesByImage: {
            ...state.boxesByImage,
            [entry.imageId]: cloneBoxes(entry.boxes),
          },
          resultsByImage: { ...state.resultsByImage, [entry.imageId]: {} },
          currentId: entry.imageId,
          selectedBoxId: entry.boxes[entry.boxes.length - 1]?.id ?? null,
        });
      },

      redo() {
        const state = get();
        const entry = state.future[state.future.length - 1];
        if (!entry) return;
        const currentBoxes = state.boxesByImage[entry.imageId] ?? [];
        set({
          future: state.future.slice(0, -1),
          past: [
            ...state.past,
            { imageId: entry.imageId, boxes: cloneBoxes(currentBoxes) },
          ],
          boxesByImage: {
            ...state.boxesByImage,
            [entry.imageId]: cloneBoxes(entry.boxes),
          },
          resultsByImage: { ...state.resultsByImage, [entry.imageId]: {} },
          currentId: entry.imageId,
          selectedBoxId: entry.boxes[entry.boxes.length - 1]?.id ?? null,
        });
      },

      setResult(boxId, result) {
        const state = get();
        if (!state.currentId) return;
        set({
          resultsByImage: {
            ...state.resultsByImage,
            [state.currentId]: {
              ...(state.resultsByImage[state.currentId] ?? {}),
              [boxId]: result,
            },
          },
        });
      },

      setResultForImage(imageId, boxId, result) {
        set((state) => ({
          resultsByImage: {
            ...state.resultsByImage,
            [imageId]: {
              ...(state.resultsByImage[imageId] ?? {}),
              [boxId]: result,
            },
          },
        }));
      },

      removeResult(boxId) {
        const state = get();
        if (!state.currentId) return;
        const results = { ...(state.resultsByImage[state.currentId] ?? {}) };
        delete results[boxId];
        set({ resultsByImage: { ...state.resultsByImage, [state.currentId]: results } });
      },

      setThreshold(value) {
        set({ threshold: value });
      },
      setPadding(value) {
        set({ padding: Math.max(0, Math.min(512, Math.round(value))) });
      },
      setPostprocess(patch) {
        set((state) => ({ postprocess: { ...state.postprocess, ...patch } }));
      },
      setShowMask(value) {
        set({ showMask: value });
      },
      setMaskOpacity(value) {
        set({ maskOpacity: value });
      },
      setViewMode(value) {
        set({ viewMode: value });
      },
      setTool(value) {
        set({ tool: value });
      },
      setAutoRun(value) {
        set({ autoRun: value });
      },
      setBusy(value) {
        set({ busy: value });
      },
      setError(value) {
        set({ error: value });
      },
    }),
    {
      name: "boxmask.session.v1",
      version: 1,
      storage: createJSONStorage(() => window.localStorage),
      partialize: (state): PersistedState => ({
        images: state.images.map(({ url: _url, ...image }) => image),
        currentId: state.currentId,
        boxesByImage: state.boxesByImage,
        selectedBoxId: state.selectedBoxId,
        threshold: state.threshold,
        padding: state.padding,
        postprocess: state.postprocess,
        showMask: state.showMask,
        maskOpacity: state.maskOpacity,
        viewMode: state.viewMode,
        autoRun: state.autoRun,
        tool: state.tool,
      }),
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<PersistedState>;
        const images = (saved.images ?? []).map((image) => ({
          ...image,
          url: undefined,
          status: "loading" as const,
        }));
        const currentId =
          saved.currentId && images.some((image) => image.id === saved.currentId)
            ? saved.currentId
            : images[0]?.id ?? null;
        const boxesByImage = saved.boxesByImage ?? {};
        const selectedBoxId =
          saved.selectedBoxId &&
          currentId &&
          (boxesByImage[currentId] ?? []).some((box) => box.id === saved.selectedBoxId)
            ? saved.selectedBoxId
            : null;
        return {
          ...current,
          ...saved,
          images,
          currentId,
          selectedBoxId,
          boxesByImage,
          resultsByImage: {},
          past: [],
          future: [],
          busy: false,
          error: null,
        };
      },
    },
  ),
);
