<script lang="ts">
  import placeholderUrl from '../../../web_front/ui/2.1.4/assets/icons/human.png';
  let { src, alt = '' }: { src: string | null; alt?: string } = $props();
  let failedSrc = $state<string | null>(null);
</script>

<img src={src && src !== failedSrc ? src : placeholderUrl} {alt} draggable="false" onerror={() => failedSrc = src} />
