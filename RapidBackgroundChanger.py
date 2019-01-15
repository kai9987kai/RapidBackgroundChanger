import win32api, win32con, win32gui
import keyboard
import platform
from tkinter import *
from tkinter import Menu
from tkinter import messagebox
import threading
import webbrowser

os = platform.release()


def callback():
    webbrowser.open_new(r"https://github.com/kai9987kai/RapidBackgroundChanger")

def update():
    window.update()
def setWallpaper(path):
    key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER, "Control Panel\\Desktop", 0, win32con.KEY_SET_VALUE)
    win32api.RegSetValueEx(key, "WallpaperStyle", 0, win32con.REG_SZ, "0")
    win32api.RegSetValueEx(key, "TileWallpaper", 0, win32con.REG_SZ, "0")
    win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, path, 1 + 2)

def Email():
    messagebox.showinfo('CONTACT', 'Email-One: kai9987kai@gmail.com \nEmail-Two:kai.piper@aol.co.uk')

def start():
    running = True
    while running:

        i = 0

        if os == "10":
            while (i <= 5):
                path = r'C:\Windows\Web\Screen\img10' + str(i) + '.jpg'
                setWallpaper(path)
                i += 1
                update()
        elif os == "7":
            while (i <= 5):
                # change the path for windows 7
                path = r'C:\Windows\Web\Screen\img10' + str(i) + '.jpg'
                setWallpaper(path)
                i += 1
                update()

        if keyboard.is_pressed('ctrl + c'):
            running = False
            break

def EXITME():
    window.destroy()
    running = False

window = Tk()
window.title("Rapid background changer")
window.geometry('350x50')
lbl = Label(window, text="Press Start \n to Spam")
lbl.grid(column=0, row=0)
lbl2 = Label(window, text="Hold the keys ctrl + c \n for emergency stop")
lbl2.grid(column=5, row=0)
btn = Button(window, text="Start", fg='green', command=start)
btn1 = Button(window, text="Stop", fg='red', command=EXITME)
btn.grid(column=1, row=0)
btn1.grid(column=2, row=0)
menu = Menu(window)
new_item = Menu(window)
new_item2 = Menu(window)
new_item2.add_command(label='Contact', command=Email)
new_item2.add_command(label='GitHub Page', command=callback)
new_item.add_command(label='Start', command=start)
new_item.add_command(label='Exit', command=EXITME)
menu.add_cascade(label='Menu', menu=new_item)
window.config(menu=menu)
menu.add_cascade(label='Help', menu=new_item2)
window.resizable(False, False)
try:
    window.iconbitmap('favicon.ico')  # Set icon
except:
    print("rip favicon")
window.mainloop()

t1 = threading.Thread(target=start)
t2 = threading.Thread(target=update)
t3 = threading.Thread(target=window)
t3 = threading.Thread(target=setWallpaper)
t1.start()
t1.join()
t2.start()
t2.join()
