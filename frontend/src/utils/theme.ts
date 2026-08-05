import { ref } from 'vue'

const theme = ref<'light' | 'dark'>(localStorage.getItem('theme') as 'light' | 'dark' || 'light')

const toggleTheme = () => {
	const newTheme: 'light' | 'dark' = theme.value === 'dark' ? 'light' : 'dark'
	applyTheme(newTheme)
}

const applyTheme = (value: 'light' | 'dark') => {
	document.documentElement.setAttribute('data-theme', value)
	localStorage.setItem('theme', value)
	theme.value = value
}

export { applyTheme, toggleTheme, theme }