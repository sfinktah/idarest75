import ida_idaapi
import ida_kernwin
import ida_loader
from idarest.idarest import idarest_plugin_t

MENU_PATH = 'Edit/Other'

def PLUGIN_ENTRY():
    globals()['instance'] = idarest_plugin_t()
    return globals()['instance']
