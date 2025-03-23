import hou
from importlib import reload
import json
import os
import Utilities
import voptoolutils

reload(Utilities)


def build_asset(kwargs):
    node = kwargs["node"]
    parm_name = kwargs["parm"].name()

    # user_data = node.userDataDict().get("megascans_user_data")
    # if not user_data:
    #     return
    # Utilities.dirty_tx_pdg(node)
    current_asset = Utilities.current_parms_eval(kwargs)["megascans_asset"]

    if current_asset == "-----":
        return

    # Define parameter groups that trigger specific actions
    material_params = {
        "megascans_asset",
        "get_path",
        "library_path",
        "reload",
        "enable_batch_process",
        "code",
    }
    geo_params = {"load_original", "file_format", "proxy_geo", "render_geo"}

    if parm_name in material_params:
        Utilities.show_background_image(kwargs)
        build_geo(kwargs)
        build_materials(kwargs)
        # Utilities.generate_tx_pdg(node)

    elif parm_name in geo_params:
        build_geo(kwargs)
        if parm_name == "render_geo":
            build_materials(kwargs)
        if parm_name == "proxy_geo":
            node.parm("tx_dict").revertToDefaults()

        # Utilities.generate_tx_pdg(node)

    elif parm_name == "resolution":
        build_materials(kwargs)
        # Utilities.generate_tx_pdg(node)

    # Force cook the node
    node.cook(force=True)

    # Cook TX PDG if necessary
    if node.parm("enable_batch_process").eval() == 0:
        Utilities.cook_tx_pdg(node)


def build_geo(kwargs):
    """
    Configures a Houdini node by setting asset file paths and related parameters.

    Args:
        kwargs (dict): A dictionary containing node-related arguments,
                       including the Houdini node reference.

    Returns:
        None
    """

    def get_filtered_files(lod_list, file_format):
        """
        Filters a list of asset files based on the specified format.

        Args:
            lod_list (list): List of file paths corresponding to a specific LOD.
            file_format (str): The desired file format (e.g., 'abc', 'fbx').

        Returns:
            list: A list of file paths that match the specified file format.
        """
        return [file for file in lod_list if file.endswith(f".{file_format}")]

    def set_geo_loader_params(node, geo_type, files):
        """
        Sets the parameters of the geometry loader node with the given asset files.

        Args:
            node (hou.Node): The Houdini node where parameters will be set.
            geo_type (str): Specifies whether the files are for "render" or "proxy" geometry.
            files (list): List of asset file paths to set.

        Returns:
            None
        """
        node.parm(f"{geo_type}_files").set(len(files))  # Set file count parameter

        for index, file in enumerate(files):
            file_parm = node.parm(f"{geo_type}_filelist{index + 1}")

            # Only update if the parameter value is different
            if file_parm.evalAsString() != file:
                file_parm.set(file)

    # Retrieve the Houdini node from the provided arguments
    node = kwargs["node"]

    # Load Megascans metadata from the node's user data
    megascans_json = node.userDataDict().get("megascans_user_data")

    if not megascans_json:  # Check if it's None or empty
        return

    megascans_data = json.loads(megascans_json)
    if not megascans_data:
        return

    # Configure batch size for processing
    batch_size = set_batch_size(kwargs, megascans_data)

    if node.parm("enable_batch_process").eval() == 0 or batch_size > 0:

        asset_info = Utilities.dump_info(kwargs, megascans_data)

        # Extract asset metadata
        asset_name = asset_info["name"]
        asset_id = asset_info["id"]

        # Get the current Houdini node parameters
        current_parms = Utilities.current_parms_eval(kwargs)
        file_format = current_parms["file_format"]

        # Determine the appropriate level of detail (LOD) for rendering
        render_lod = (
            "HIGH"
            if node.parm("load_original").eval() == 1
            and not node.parm("load_original").isDisabled()
            else current_parms["render_geo"]
        )

        # Retrieve and filter render geometry files based on the format
        render_geo_files = get_filtered_files(
            asset_info["lods"][render_lod], file_format
        )
        set_geo_loader_params(node, "render", render_geo_files)

        # Retrieve and filter proxy geometry files based on the format
        proxy_geo_files = get_filtered_files(
            asset_info["lods"][current_parms["proxy_geo"]], file_format
        )
        set_geo_loader_params(node, "proxy", proxy_geo_files)

        # Set the format switch parameter (0 for 'abc', 1 for others)
        node.parm("format_switch").set(0 if file_format == "abc" else 1)

        # Set the asset name parameter using asset name and ID
        node.parm("asset_name").set(f"{asset_name}_{asset_id}")

        index_node = hou.node(f"{node.path()}/sopnet/INDEX")
        var_num = index_node.geometry().attribValue("max_index") + 1
        node.parm("var_num_message").set(f"Number of Variants: {var_num}")
        node.parm("var_num").set(var_num)


def build_materials(kwargs):
    """
    Build materials based on the asset's material data.

    Args:
        node (hou.Node): Houdini node containing Megascans asset data.
    """
    node = kwargs["node"]  # Load Megascans metadata from the node's user data
    megascans_json = node.userDataDict().get("megascans_user_data")

    if not megascans_json:  # Check if it's None or empty
        return

    megascans_data = json.loads(megascans_json)
    if not megascans_data:
        return
    matlib = hou.node(node.path() + "/material_library")
    matlib.deleteItems(matlib.children())
    create_matlib_content(kwargs)


def create_matlib_content(kwargs):
    node = kwargs["node"]
    matlib = hou.node(node.path() + "/material_library")
    kma_shader = voptoolutils._setupMtlXBuilderSubnet(
        destination_node=matlib,
        name="kma_shader",
        mask=voptoolutils.KARMAMTLX_TAB_MASK,
        folder_label="Karma Material Builder",
        render_context="kma",
    )
    preview_shader = voptoolutils._setupUsdPreviewBuilderSubnet(
        destination_node=matlib,
    )

    kma_shader.setGenericFlag(hou.nodeFlag.Material, False)
    collect = matlib.createNode("collect", "OUT_material")

    collect.setInput(0, kma_shader, 0)
    collect.setInput(1, kma_shader, 1)
    collect.setInput(2, kma_shader, 2)

    matlib.layoutChildren(horizontal_spacing=2)
    create_image_files(kwargs, kma_shader)


def set_batch_size(kwargs, megascans_data):
    node = kwargs["node"]
    batch_process = node.parm("enable_batch_process").eval()
    batch_size_parm = node.parm("stringvalues")
    batch_size_parm.set(0)

    if batch_process:
        asset_ids = set(node.parm("batch_ids").evalAsString().split())

        if not asset_ids:  # No need to proceed if asset_ids is empty
            return 0

        filtered_ids = [
            asset.lower().split("::")[-1]
            for asset in megascans_data
            if asset.lower().split("::")[-1] in asset_ids
        ]

        batch_size = len(filtered_ids)
        batch_size_parm.set(batch_size)

        for index, asset_id in enumerate(filtered_ids, start=1):
            node.parm(f"stringvalue{index}").set(asset_id)

        return batch_size

    current_parms = Utilities.current_parms_eval(kwargs)
    current_asset = current_parms["megascans_asset"]
    asset_id = current_asset.split("::")[-1]

    batch_size_parm.set(1)
    node.parm("stringvalue1").set(asset_id)

    return 1


def filter_tx_file(texture):
    # node = kwargs["node"]
    # if not textures:
    #     textures = get_textures(kwargs)
    # to_generate = {}
    # for tx in textures:
    # rat_file = os.path.splitext(tx[1])[0] + ".rat"
    rat_file = os.path.splitext(texture)[0] + ".rat"
    if not os.path.exists(rat_file):
        return texture
        # to_generate[tx[0]] = tx[1]
    return rat_file

    # node.parm("dictattribs").set(0)
    # if to_generate:
    #     node.parm("dictattribs").set(1)
    #     node.parm("dictname1").set("textures")
    #     node.parm("dictvalue1").set(json.dumps(to_generate))
    #     return to_generate
    # return None


def get_textures(kwargs):
    """
    Set the current textures for the asset based on resolution and LOD.

    Args:
        megascans_data (dict): Data containing textures for the current asset.

    Returns:
        list: A list of tuples containing texture type, file path, and colorspace.
    """
    node = kwargs["node"]
    textures_dict = json.loads(node.parm("asset_info").evalAsString())["textures"]
    render_geo_lod = Utilities.current_parms_eval(kwargs)["render_geo"]
    current_res = Utilities.current_parms_eval(kwargs)["resolution"]
    current_textures = []
    to_generate = {}

    # Loop through each texture type and select the appropriate resolution
    for tx_type, tx_type_values in textures_dict.items():
        textures = tx_type_values["resolution"][current_res]
        # Select texture matching the LOD, fallback to the first if no match found
        found_tx = next(
            (texture for texture in textures if render_geo_lod in texture),
            textures[0],
        )
        exr_file = os.path.splitext(found_tx)[0] + ".exr"
        if os.path.exists(exr_file):
            found_tx = exr_file

        if filter_tx_file(found_tx) == found_tx:
            to_generate[tx_type] = found_tx
        else:
            found_tx = filter_tx_file(found_tx)

        current_textures.append((tx_type, found_tx, tx_type_values["colorSpace"]))

    node.parm("tx_dict").revertToDefaults()

    if to_generate:
        # node.parm("dictattribs").set(1)
        # node.parm("dictname1").set("textures")
        node.parm("tx_dict").set(json.dumps(to_generate))

    return current_textures


def create_image_files(kwargs, shader):
    node = kwargs["node"]
    textures = get_textures(kwargs)
    surface = hou.node(shader.path() + "/mtlxstandard_surface")
    displacement = hou.node(shader.path() + "/mtlxdisplacement")
    not_used_textures = []

    for texture in textures:
        tx_type, tx_path, tx_colorspace = texture
        tx_image = shader.createNode("mtlximage", tx_type.upper())
        tx_image.parm("file").set(tx_path)
        tx_image.setColor(hou.Color((0.71, 0.518, 0.004)))
        if tx_type.lower() == "albedo":
            surface.setNamedInput("base_color", tx_image, "out")
        elif tx_type.lower() == "roughness":
            surface.setNamedInput("specular_roughness", tx_image, "out")
        elif tx_type.lower() == "normal":
            normal_map = shader.createNode("mtlxnormalmap")
            normal_map.parm("scale").set(0.01)
            normal_map.setInput(0, tx_image)
            surface.setNamedInput("normal", normal_map, "out")
        elif tx_type.lower() == "displacement":
            tx_image.parm("signature").set("float")
            displacement.parm("scale").set(0.01)
            remap = shader.createNode("mtlxremap")
            remap.parm("outlow").set(-0.5)
            remap.parm("outhigh").set(0.5)
            remap.setInput(0, tx_image)
            displacement.setNamedInput("displacement", remap, "out")
        elif tx_type.lower() in surface.inputNames():
            surface.setNamedInput(tx_type.lower(), tx_image, "out")
        else:
            not_used_textures.append(tx_image)

    layout_matnet(shader, not_used_textures)


def layout_matnet(shader, not_used_textures):
    """
    Clean up the shader network by removing unused texture nodes and organizing the layout.

    Args:
        shader (hou.Node): Shader node containing texture nodes to clean up.
        not_used_textures (list): List of unused texture image nodes.
    """
    shader.layoutChildren(horizontal_spacing=2)

    # Create a network box for unused textures and arrange their layout
    networkbox = shader.createNetworkBox()
    for image in not_used_textures:
        networkbox.addItem(image)
    networkbox.fitAroundContents()
    networkbox.setMinimized(True)
    # networkbox.setPosition((min_pos[0], min_pos[1] - 3))
    networkbox.setComment("Textures Not Used")
