from importlib import reload
from collections import namedtuple
import json
import os
import hou
import voptoolutils
import Utilities

reload(Utilities)


def build_asset(kwargs):
    """
    Main function to build an asset in Houdini using provided node context.

    Args:
        kwargs (dict): A dictionary containing Houdini node under the key "node".
    """

    def cook_pdg_network(node):
        """
        Cooks the PDG (Procedural Dependency Graph) network related to the asset.

        Args:
            node (hou.Node): The current Houdini node.
        """
        # Locate the PDG top node inside the current node
        top_node = hou.node(f"{node.path()}/build_asset")
        # Mark all work items as dirty to trigger re-cook
        top_node.dirtyAllWorkItems(False)
        # Cook the PDG network and optionally save output
        top_node.cookOutputWorkItems(save_prompt=True)

    node = kwargs["node"]

    # Show the background image if available
    Utilities.show_background_image(node)

    # Build geometry; only proceed if successful
    result = build_geo(node)

    if result:
        # Build materials and cook the PDG network
        build_materials(node)
        cook_pdg_network(node)


def build_geo(node):
    """
    Loads and configures geometry files for the asset based on user settings and LODs.

    Args:
        node (hou.Node): The Houdini node that holds asset parameters and UI.

    Returns:
        bool: True if geometry setup is successful, False otherwise.
    """

    def get_filtered_files(lod_list, file_format):
        """
        Filters files in a given LOD list based on the desired file format.

        Args:
            lod_list (list): List of file names.
            file_format (str): Desired file extension (e.g., 'abc', 'fbx').

        Returns:
            list: Filtered list of files matching the format.
        """
        return [file for file in lod_list if file.endswith(f".{file_format}")]

    def set_geo_loader_params(node, geo_type, files):
        """
        Sets geometry loader parameters for render or proxy geometry.

        Args:
            node (hou.Node): Houdini node to set parameters on.
            geo_type (str): Either "render" or "proxy".
            files (list): List of file paths to load.
        """
        # Set the file count parameter
        node.parm(f"{geo_type}_files").set(len(files))

        for index, file in enumerate(files):
            file_parm = node.parm(f"{geo_type}_filelist{index + 1}")
            # Only set the parm if it doesn't already match
            if file_parm.evalAsString() != file:
                file_parm.set(file)

    megascans_user_data = None
    # Get user-defined paths from node
    current_paths = Utilities.get_current_paths(node)

    # Load Megascans metadata if available
    if current_paths.user_data_path.exists():
        with open(current_paths.user_data_path, "r", encoding="utf-8") as f:
            megascans_user_data = json.load(f)

    if megascans_user_data is None:
        return False

    # Extract useful metadata from Megascans user data
    asset_info = Utilities.dump_info(node, megascans_user_data)
    asset_name = asset_info["name"]
    asset_id = asset_info["id"]

    current_parms = Utilities.get_current_parms(node)
    file_format = current_parms.file_format

    # Determine which LOD to use for render geo
    render_lod = (
        "HIGH"
        if node.parm("load_original").eval() == 1
        and not node.parm("load_original").isDisabled()
        else current_parms.render_geo
    )

    # Load render geometry files
    render_geo_files = get_filtered_files(asset_info["lods"][render_lod], file_format)
    set_geo_loader_params(node, "render", render_geo_files)

    # Load proxy geometry files
    proxy_geo_files = get_filtered_files(
        asset_info["lods"][current_parms.proxy_geo], file_format
    )
    set_geo_loader_params(node, "proxy", proxy_geo_files)

    # Set the format switch parm: 0 for abc, 1 for others
    node.parm("format_switch").set(0 if file_format == "abc" else 1)

    # Set asset name with ID
    node.parm("asset_name").set(f"{asset_name}_{asset_id}")

    # Set the number of geometry variants from the INDEX node
    var_num = (
        hou.node(f"{node.path()}/sopnet/INDEX").geometry().attribValue("max_index") + 1
    )
    node.parm("var_num_message").set(f"Number of Variants: {var_num}")
    node.parm("var_num").set(var_num)

    return True


def build_materials(node):
    matlib = hou.node(node.path() + "/material_library")
    matlib.deleteItems(matlib.children())
    use_saved_shader = Utilities.get_current_parms(node).save_shader_state
    create_matlib_content(node, use_saved_shader)


def create_matlib_content(node, use_saved_shader):
    def create_image_files(node, shader, use_saved_shader):
        def layout_matnet(shader, not_used_textures):
            shader.layoutChildren(horizontal_spacing=2)

            # Create a network box for unused textures and arrange their layout
            networkbox = shader.createNetworkBox()
            for image in not_used_textures:
                networkbox.addItem(image)
            networkbox.fitAroundContents()
            networkbox.setMinimized(True)
            # networkbox.setPosition((min_pos[0], min_pos[1] - 3))
            networkbox.setComment("Textures Not Used")

        texture_info = get_textures(node)
        surface = hou.node(shader.path() + "/mtlxstandard_surface")
        displacement = hou.node(shader.path() + "/mtlxdisplacement")
        not_used_textures = []

        # Normalize texture list
        for tx_type, tx_path in texture_info.current_textures:
            tx_type_lower = tx_type.lower()

            # Create mtlximage node
            tx_image = shader.createNode("mtlximage", tx_type)
            tx_image.parm("file").set(tx_path)
            tx_image.setColor(hou.Color((0.71, 0.518, 0.004)))

            if tx_type_lower == "albedo":
                surface.setNamedInput("base_color", tx_image, "out")

            elif tx_type_lower == "roughness":
                surface.setNamedInput("specular_roughness", tx_image, "out")

            elif tx_type_lower == "normal":
                normal_map = shader.createNode("mtlxnormalmap")
                normal_map.setInput(0, tx_image)
                surface.setNamedInput("normal", normal_map, "out")

            elif tx_type_lower == "displacement":
                tx_image.parm("signature").set("float")
                displacement.parm("scale").set(0.01)

                remap = shader.createNode("mtlxremap")
                remap.parm("outlow").set(-0.5)
                remap.parm("outhigh").set(0.5)
                remap.setInput(0, tx_image)

                displacement.setNamedInput("displacement", remap, "out")

            elif tx_type_lower in surface.inputNames():
                surface.setNamedInput(tx_type_lower, tx_image, "out")

            else:
                not_used_textures.append(tx_image)

        layout_matnet(shader, not_used_textures)

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
    create_image_files(node, kma_shader, use_saved_shader)


def get_textures(node):
    """
    Set the current textures for the asset based on resolution and LOD.

    Args:
        megascans_data (dict): Data containing textures for the current asset.

    Returns:
        list: A list of tuples containing texture type, file path, and colorspace.
    """

    def filter_tx_file(texture):
        rat_file = os.path.splitext(texture)[0] + ".rat"
        if not os.path.exists(rat_file):
            return texture
        return rat_file

    TextureInfo = namedtuple("TextureInfo", ["current_textures", "to_generate"])
    textures_dict = json.loads(node.parm("asset_info").evalAsString())["textures"]
    current_parms = Utilities.get_current_parms(node)
    render_geo_lod = current_parms.render_geo
    current_res = current_parms.resolution
    current_textures = []
    to_generate = []

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
            to_generate.append((tx_type, found_tx))
        else:
            found_tx = filter_tx_file(found_tx)

        current_textures.append((tx_type, found_tx))

    return TextureInfo(current_textures, to_generate)


def set_batch_size(node):
    batch_process = node.parm("enable_batch_process").eval()
    batch_size_parm = node.parm("stringvalues")
    batch_size_parm.set(0)

    if batch_process:
        asset_ids = set(node.parm("batch_ids").evalAsString().split())

        if not asset_ids:  # No need to proceed if asset_ids is empty
            return 0

        # filtered_ids = [
        #     asset.lower().split("::")[-1]
        #     for asset in megascans_data
        #     if asset.lower().split("::")[-1] in asset_ids
        # ]

        labels = node.parm("megascans_asset").menuLabels()
        batch_size = len(labels)
        batch_size_parm.set(batch_size)

        for index, asset_id in enumerate(labels, start=1):
            node.parm(f"stringvalue{index}").set(asset_id.lower().split("::")[-1])

        return batch_size

    current_parms = Utilities.get_current_parms(node)
    asset_id = current_parms.megascans_asset.split("::")[-1]

    batch_size_parm.set(1)
    node.parm("stringvalue1").set(asset_id.lower().split("::")[-1])

    return 1
