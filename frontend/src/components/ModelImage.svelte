<script lang="ts">
  import placeholderUrl from '../assets/human.png';
  let { src, alt = '' }: { src: string | null; alt?: string } = $props();
  let failedSrc = $state<string | null>(null);
</script>

<img src={src && src !== failedSrc ? src : placeholderUrl} {alt} draggable="false" onerror={() => failedSrc = src} />
