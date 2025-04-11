import os
from time import sleep
from datetime import datetime

if os.name == 'nt':
    import msvcrt
else:
    import sys
    import termios
    import atexit
    from select import select
    unix_stdin_fd = 0
    unix_old_term = None

### BASICS ###

def getch():
    if os.name == 'nt':
        return msvcrt.getch().decode('utf-8')
    else:
        return sys.stdin.read(1)

def kbhit():
    if os.name == 'nt':
        return msvcrt.kbhit()
    else:
        dr, dw, de = select([sys.stdin], [], [], 0)
        return dr != []

def setup():
    # support normal-terminal reset at exit
    atexit.register(cleanup)
    if os.name == 'nt':
        os.system('') # enable ansi
    else:
        # save the terminal settings
        global unix_stdin_fd
        global unix_old_term
        unix_stdin_fd = sys.stdin.fileno()
        unix_new_term = termios.tcgetattr(unix_stdin_fd)
        unix_old_term = termios.tcgetattr(unix_stdin_fd)
        # new terminal setting unbuffered
        unix_new_term[3] = (unix_new_term[3] & ~termios.ICANON & ~termios.ECHO)
        termios.tcsetattr(unix_stdin_fd, termios.TCSAFLUSH, unix_new_term)
    # setup ansi after enabling
    switch_buffer()
    cursor(0)

cleaned_up = False

def cleanup(quitting=False):
    global cleaned_up
    if cleaned_up: return
    cleaned_up = True
    cursor()
    if not quitting:
        try: input('press enter to quit...')
        except KeyboardInterrupt: pass
    switch_buffer(0)
    if os.name != 'nt' and unix_old_term is not None:
        termios.tcsetattr(unix_stdin_fd, termios.TCSAFLUSH, unix_old_term)

def quit():
    cleanup(True)
    exit()

# no newline output
def text(*args, **kwargs):
	print(*args, **kwargs, end='')

# flush
def flush(): print(end='', flush=True)

# keyboard input
def read_key():
    special_keys = {
        '\b': 'backspace',
        '\t': 'tab',
        '\n': 'enter',
        '\r': 'enter',
        '\x1b': 'esc'
    }

    flush()
    key = getch()
    if key in special_keys:
        key = special_keys[key]
    return key

# generate ANSI sequence
def esc(params): return f'\x1b[{params}'

# execute ANSI sequence
def seq(params): print(f'\x1b[{params}', end='')

### ANSI SEQUENCES ###

def clear(): switch_buffer()

def switch_buffer(on=True): seq('?1049'+'lh'[on])

# set cursor position
def cjump(x=0, y=0):
	if x and y: seq(f'{y};{x}H')
	elif x: seq(f'{x}G')
	elif y: seq(f'{y}d')

# adjust cursor position
def cmove(x=0, y=0):
	if y < 0: seq(f'{-y}A')
	elif y: seq(f'{y}B')
	if x > 0: seq(f'{x}C')
	elif x: seq(f'{-x}D')

# get cursor position
def cpos():
	seq('6n')
	coords = ''
	flush()
	char = getch()
	while char != '\x1b':
		char = getch()
	while char != 'R':
		coords += char
		char = getch()
	return [int(c) for c in coords[2:].split(';')][::-1]

# save cursor position
def csave(): seq('s')

# restore cursor position
def crestore(): seq('u')

# show/hide cursor
def cursor(show=True): seq('?25'+'lh'[show])

# colored text
def color(code, bg=False):
	colors = [code[1:3],code[3:5],code[5:]]
	colors = ';'.join([str(int(c,16)) for c in colors])
	return f'\x1b[{3+bg}8;2;{colors}m'

### EDITOR ###

# jump to editor position
def jump_to_edit():
	cjump(0,settings['code window pos'][1]+edit[1])
	cjump(settings['code window pos'][0]+edit[0])

# process pressed keyboard key
def process_key(key):
	global edit
	if key == 'enter':
		text(f'\n\x1b[{settings["code window pos"][0]}G')
		edit = [0, edit[1]+1]
		code.append('')
	elif key == 'backspace':
		if edit != [0, 0]:
			text('\b \b')
			edit[0] -= 1
			remove(edit)
	else:
		text(key)
		insert(key, edit)
		edit[0] += 1

# insert characters
def insert(chars, edit):
	line = code[edit[1]]
	line = line[:edit[0]] + chars + line[edit[0]:]
	code[edit[1]] = line

# remove character
def remove(edit):
	line = code[edit[1]]
	line = line[:edit[0]] + line[edit[0]+1:]
	code[edit[1]] = line

### INTERPRETER ###

# initialize interface before interpreting
def initialize(settings):
    clear()
    cursor(0)

    # black title with colored background
    def display_title(title, bg):
    	cmove(0, -1)
    	text(f'{color(bg, 1)}\x1b[30m {title} \x1b[0m')

    # memory display
    cjump(*settings['mem display pos'])
    text(' ')
    display_title('memory', '#ffd541')
    cjump(*settings['mem display pos'])
    text(color('#849be4'))
    text('╭\x1b[1B\b│\x1b[1B\b╰')
    for i in range(settings['mem size']):
	    text('\x1b[2A──┬\x1b[1B\b\b\b00│\x1b[1B\b\b\b──┴')
    text('\x1b[2A\b╮\x1b[2B\b╯')

	# code window
    cjump(*settings['code window pos'])
    display_title('code', '#e86a9b')
    cjump(*settings['code window pos'])
    text('\x1b[1B\x1b[3G'.join(code))

    # terminal
    cjump(*settings['terminal pos'])
    display_title('terminal', '#59c135')

# interpret brainfuck code
def interpret(code, settings):
	# memory
	mem_size = settings['mem size']
	mem = [0] * mem_size

	# pointers
	cp, mp = 0, 0

	# display positions
	mem_pos = settings['mem display pos']
	code_pos = settings['code window pos']
	cjump(*settings['terminal pos'])
	csave()

	# colors
	mem_grid_color = color('#849be4')
	mem_pointer_color = color('#ffc400')
	code_pointer_color = '\x1b[30;'+color('#e86a9b', 1)[2:]

	# memory pointer
	def draw_mem_pointer():
		jump = f'\x1b[{mem_pos[1]};{mem_pos[0]+3*mp}H'
		pointer = '╭──╮\x1b[1B\x1b[4D│\x1b[2C│\x1b[1B\x1b[4D╰──╯'
		text(f'{jump}{mem_pointer_color}{pointer}\x1b[0m')

	def erase_mem_pointer():
		jump = f'\x1b[{mem_pos[1]};{mem_pos[0]+3*mp}H'
		l = ['┬┴','╭╰'][mp==0]
		r = ['┬┴','╮╯'][mp==mem_size-1]
		nl = '\x1b[1B\x1b[4D'
		pointer = f'{l[0]}──{r[0]}{nl}│\x1b[2C│{nl}{l[1]}──{r[1]}'
		text(f'{jump}{mem_grid_color}{pointer}')

	draw_mem_pointer()

	# memory display cells
	def update_cell():
		jump = f'\x1b[{mem_pos[1]+1};{mem_pos[0]+3*mp+1}H'
		text(jump+mem_grid_color*(mem[mp]==0)+f'{mem[mp]:02x}\x1b[0m')

	# code pointer
	def draw_code_pointer():
		pos = [code_pos[0]+cp-nls[-1]-1, code_pos[1]+len(nls)-1]
		jump = f'\x1b[{pos[1]};{pos[0]}H'
		text(f'{jump}{code_pointer_color}{code[cp]}\x1b[0m')
		return jump+code[cp]

	# newlines
	nls = [-1]

	# line ending handling
	line_ending = False

	# ANSI sequence handling
	sequence = ''
	styles = ['', '', '']  # styles applied to output text

	# execution time measurement
	exec_start = datetime.now()
	input_time = 0

	instructions = 0

	cjump(100, 20)
	while cp < len(code):

		cmd = code[cp]
		instructions += 1

		# draw code pointer
		code_pointer_erase = draw_code_pointer()

		if cmd == '+':
			mem[mp] = [mem[mp]+1,0][mem[mp]==255]
			update_cell()
		elif cmd == '-':
			mem[mp] = [mem[mp]-1,255][mem[mp]==0]
			update_cell()
		elif cmd == '>':
			erase_mem_pointer()
			mp = [mp+1,0][mp==mem_size-1]
			draw_mem_pointer()
		elif cmd == '<':
			erase_mem_pointer()
			mp = [mp-1,mem_size-1][mp==0]
			draw_mem_pointer()
		elif cmd == '.':
			crestore()
			char = chr(mem[mp])
			if sequence:
				sequence += char
				if ord(char) > 64 and char != '[':
					styles = apply_sequence(sequence, styles)
					sequence = ''
			else:
				if styles: text(''.join(styles))
				if char in '\r\n':
					if not line_ending:
						cmove(0, 1)
						cjump(settings['terminal pos'][0])
						line_ending = True
					else:
						line_ending = False
				elif char == '\x1b': sequence = '\x1b'
				else:
					text(char)
					line_ending = False
				if styles: text('\x1b[0m')
			csave()
		elif cmd == ',':
			flush()
			crestore()
			cursor(1)
			input_start = datetime.now()
			mem[mp] = ord(getch())
			input_end = datetime.now()
			input_time+=(input_end-input_start).total_seconds()
			cursor(0)
			csave()
			update_cell()
		elif cmd == '[':
			if not mem[mp]:
				brackets = 1
				while brackets:
					cp += 1
					if code[cp] == '[': brackets += 1
					elif code[cp] == ']': brackets -= 1
					elif code[cp] == '\n': nls.append(cp)
		elif cmd == ']':
			if mem[mp]:
				brackets = 1
				while brackets:
					cp -= 1
					if code[cp] == '[': brackets -= 1
					elif code[cp] == ']': brackets += 1
					elif code[cp] == '\n': nls.pop()
		elif cmd == '\n':
			nls.append(cp)
			instructions -= 1
		else: instructions -= 1

		# erase code pointer
		text(code_pointer_erase)

		cp += 1

	# calculating execution time
	exec_time = datetime.now() - exec_start
	exec_time = exec_time.total_seconds()-input_time
	exec_time = int(exec_time*1000)/1000

	cjump(*settings['terminal pos'])
	cmove(len('terminal')+3, -1)
	text(color('#59c135'))
	text(f'{exec_time} sec. {instructions} ins.\x1b[0m')

# apply virtual console ANSI sequence
def apply_sequence(seq, styles):
	term = seq[-1]

	# terminal position
	tpos = settings['terminal pos']

	# cursor control
	if term == 'A':
		dist = int(seq[2:-1])
		# prevent from going out of bounds
		if cpos()[1] - dist < tpos[1]: text(f'\x1b[{tpos[1]}d')
		else: text(seq)
	elif term == 'D':
		dist = int(seq[2:-1])
		# prevent from going out of bounds
		if cpos()[0] - dist < tpos[0]: text(f'\x1b[{tpos[0]}G')
		else: text(seq)

	# style and color control
	elif term == 'm':
		style = int(seq[2:-1])
		if style == 0: styles = [''] * 3
		elif style in range(40, 48) or style in range(100, 108):
			styles[1] = seq

	else:
		text(seq)

	return styles

settings = {
	'mem size': 48,
	'mem display pos': [2, 2],
	'code window pos': [3, 7],
	'terminal pos': [104, 7],
}

# import code from file
with open('square.bf', 'r') as code_file:
	code = code_file.read()
	code = code.replace('\t', ' '*4)
	code = code.split('\n')

setup()

initialize(settings)

# editor cursor position
edit = [len(code[-1]), len(code)-1]

jump_to_edit()
cursor()
csave()

running = True
while running:
    key = read_key()
    print(key)
    if key == '`':
        initialize(settings)
        interpret('\n'.join(code), settings)
        jump_to_edit()
        cursor()
        csave()
    elif key == 'esc':
        running = False
    else: # send to editor
        process_key(key)
        csave()

quit()
