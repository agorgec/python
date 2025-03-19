import hou
from importlib import reload
import MegascansData, Build, Utilities

reload(MegascansData)
reload(Build)
reload(Utilities)

# Get the current Houdini node
node = kwargs["node"]

# Evaluate the parameter 'library_path'
library_path = node.parm("library_path").evalAsString()

# Initialize the MegascansData
MegascansData.set_megascans_data(kwargs, library_path)
Utilities.dirty_tx_pdg(node)
