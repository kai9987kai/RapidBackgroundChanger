import win32api, win32con, win32gui
import keyboard
from tkinter import *
from tkinter import Menu
from tkinter import messagebox

def setWallpaper(path):
    key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER, "Control Panel\\Desktop", 0, win32con.KEY_SET_VALUE)
    win32api.RegSetValueEx(key, "WallpaperStyle", 0, win32con.REG_SZ, "0")
    win32api.RegSetValueEx(key, "TileWallpaper", 0, win32con.REG_SZ, "0")
    win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, path, 1 + 2)
def EXITME():
    exit(0)  # crashed prog so it closes
    # strtoint("crashmE!")
def Email():
    messagebox.showinfo('CONTACT', 'Email-One: kai9987kai@gmail.com \nEmail-Two:kai.piper@aol.co.uk')
def start():
    running = True
    while running:
        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img100.jpg'
            setWallpaper(path)

        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img101.jpg'
            setWallpaper(path)

        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img105.jpg'
            setWallpaper(path)

        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img102.jpg'
            setWallpaper(path)

        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img103.jpg'
            setWallpaper(path)

        if __name__ == "__main__":
            path = r'C:\Windows\Web\Screen\img104.jpg'
            setWallpaper(path)

        if keyboard.is_pressed('c'):
            break
window = Tk()
window.title("Rapid background changer")
window.geometry('350x50')
lbl = Label(window, text="Press Start \n to Spam")
lbl.grid(column=0, row=0)
lbl2 = Label(window, text="Hold the keys ctrl + c \n for emergency stop")
lbl2.grid(column=5, row=0)
btn = Button(window, text="Start",fg='green', command = start)
btn1 = Button(window, text="Stop",fg='red', command = EXITME)
btn.grid(column=1, row=0)
btn1.grid(column=2, row=0)
menu = Menu(window)
new_item = Menu(window)
new_item2 = Menu(window)
new_item2.add_command(label='Contact', command=Email)
new_item.add_command(label='Start', command=start)
new_item.add_command(label='Exit', command=EXITME)
menu.add_cascade(label='Menu', menu=new_item)
window.config(menu=menu)
menu.add_cascade(label='Help', menu=new_item2)
window.resizable(False, False)
window.iconbitmap('favicon.ico')  # Set icon
window.mainloop()
