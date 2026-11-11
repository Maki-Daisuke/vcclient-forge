<script lang="ts">
  import type { Snippet } from 'svelte';
  import { useSession } from '../lib/session.svelte';
  import { useUi } from '../lib/ui.svelte';
  let { label, children }: { label: string; children: Snippet } = $props();
  const session = useSession();
  const ui = useUi();
  const tooltipId = $props.id();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex: The disabled control's explanation must be keyboard accessible. -->
<div class="start-button-wrapper inference-setting" role={session.active === true ? 'group' : undefined}
  aria-label={session.active === true ? label : undefined} tabindex={session.active === true ? 0 : undefined}
  aria-describedby={session.active === true ? tooltipId : undefined}>
  {@render children()}
  {#if session.active === true}<span id={tooltipId} class="start-tooltip" role="tooltip">{ui.t('forge.client_processing_stopped')}</span>{/if}
</div>

<style>
  .inference-setting { display: block; min-width: 0; }
</style>
