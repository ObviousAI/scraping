import pyautogui

import time

width, height = pyautogui.size()
print(f"Screen width: {width}, Screen height: {height}")


while (True):
    x, y = 350, 190
    time.sleep(4)
    pyautogui.moveTo(x, y)

    time.sleep(1)
    pyautogui.click()


    time.sleep(5)

    x, y = 340, 430
    time.sleep(1)
    pyautogui.moveTo(x, y)

    time.sleep(1)
    pyautogui.click()

    time.sleep(900)