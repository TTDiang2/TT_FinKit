/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#FFFFFF', 'bg-secondary': '#FAFAFA', 'bg-tertiary': '#F5F5F5', 'bg-sidebar': '#F8F8F8',
        'border-default': '#E8E8E8', 'border-hover': '#D4D4D4',
        'text-primary': '#1A1A1A', 'text-secondary': '#6B6B6B', 'text-muted': '#9B9B9B',
        'accent-primary': '#000000', 'accent-hover': '#333333', 'accent-light': '#F5F5F5',
        'income-color': '#F44336', 'expense-color': '#4CAF50', 'transfer-color': '#2196F3',
        success: '#4CAF50', warning: '#FF9800', error: '#F44336', info: '#2196F3',
      },
      fontFamily: { sans: ['Inter', 'sans-serif'], mono: ['JetBrains Mono', 'monospace'] },
      borderRadius: { 'sm': '4px', 'md': '8px', 'lg': '12px', 'xl': '16px' },
      boxShadow: { 'sm': '0 1px 2px rgba(0,0,0,0.04)', 'md': '0 2px 8px rgba(0,0,0,0.06)', 'lg': '0 4px 16px rgba(0,0,0,0.10)', 'xl': '0 8px 32px rgba(0,0,0,0.14)' },
    },
  },
  plugins: [],
}