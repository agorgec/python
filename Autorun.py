import hou
from importlib import reload
import MegascansData

reload(MegascansData)

# Get the current Houdini node (pwd refers to 'print working directory')
node = hou.pwd()

# Evaluate the parameter 'library_path' on the node, which likely points to the asset library
library_path = node.parm("library_path").evalAsString()

# Initialize the MegascansData object and retrieve the data dictionary
MegascansData.set_megascans_data(node, library_path)
