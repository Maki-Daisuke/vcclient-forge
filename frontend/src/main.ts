import { mount } from 'svelte';
import App from './App.svelte';
import LogWindow from './components/LogWindow.svelte';
import './app.css';

mount(new URLSearchParams(location.search).get('view') === 'log' ? LogWindow : App, { target: document.getElementById('app')! });
