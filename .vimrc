" Make Vim more useful
set nocompatible
" Use UTF-8 without BOM
set encoding=utf-8 nobomb
" Use the OS clipboard by default (on versions compiled with `+clipboard`)
set clipboard=unnamed
" Backspace over autoindent, line breaks, and start of insert (set here too,
" since hosts without a system vimrc don't get it by default)
set backspace=indent,eol,start

" Centralize backups, swapfiles and undo history. Trailing // encodes the
" file's full path into the swap/undo name, so same-basename files in
" different repos (config, main.yml, ...) don't collide on one swapfile.
set backupdir=~/.vim/backups//
set directory=~/.vim/swaps//
set undodir=~/.vim/undo//
set undofile

" Don't create backups when editing files in certain directories
set backupskip=/tmp/*,/private/tmp/*

" Respect modeline in files
set modeline
set modelines=4

" Enable syntax highlighting and filetype plugins
syntax on
filetype plugin indent on

" Colorscheme (silent! so a missing scheme doesn't error at startup)
silent! colorscheme onedark

" Enable relative line numbers
set number relativenumber
" Highlight current line
set cursorline
" Make tabs as wide as two spaces (softtabstop so Backspace eats a full indent)
set expandtab tabstop=2 shiftwidth=2 softtabstop=2
" Show "invisible" characters (tab, trailing space, nbsp)
set lcs=tab:▸\ ,trail:·,nbsp:_
set list
" Ignore case of searches, unless an uppercase letter is used
set ignorecase smartcase
" Highlight dynamically as pattern is typed
set incsearch hlsearch
" Show the pending command and the size of the visual selection
set showcmd
" Allow switching away from a modified buffer without saving
set hidden

" Keep context lines visible above/below/around the cursor
set scrolloff=5 sidescrolloff=5

" Better command-line completion
set wildmenu
set wildmode=longest:full,full
set wildignore+=*.pyc,*.o,*.so,.git/*,node_modules/*,.venv/*

" New splits open to the right / below (matches reading order)
set splitright splitbelow

" Faster updates for CursorHold, swap writes, plugin signals
set updatetime=300

" Reload files changed outside Vim (pairs with the short updatetime above)
set autoread

" Don't wait on terminal key codes, so <Esc> leaves insert mode promptly
set ttimeout ttimeoutlen=100

" Show the sign column only when something populates it (no sign plugins yet)
set signcolumn=auto

" Enable fzf plugin
set rtp+=~/.zsh/fzf

" Reselect visual block after indent (so > > > works without re-selecting)
xnoremap < <gv
xnoremap > >gv

" Wrap guide at 72 cols for commit message bodies
autocmd FileType gitcommit setlocal colorcolumn=72
