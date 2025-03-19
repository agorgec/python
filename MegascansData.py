import os, re, json
from pathlib import Path
from importlib import reload
import Utilities

reload(Utilities)


def set_megascans_data(kwargs, library_path):
    """
    Loads Megascans asset metadata from a JSON file and assigns it to the given Houdini node.

    Args:
        node (hou.Node): The Houdini node to store asset metadata and trigger updates.
        library_path (str or Path): The root path of the Megascans library.

    Returns:
        None
    """
    # Define the path to the JSON file containing downloaded asset metadata
    assets_data_path = Path(library_path) / "Downloaded" / "assetsData.json"

    # Dictionary to store processed Megascans asset metadata
    megascans_data = {}

    # Check if the asset metadata file exists
    if os.path.isfile(assets_data_path):
        # Open and read the asset data JSON file
        with open(assets_data_path, "r", encoding="utf-8") as file:
            assets_data = json.load(file)  # Load asset data into a dictionary

        # Iterate over each asset entry in the JSON data
        for data in assets_data:
            # Normalize asset name by replacing spaces with underscores
            asset_name = "_".join(data["name"].split())
            asset_type = data[
                "type"
            ]  # Asset type (e.g., 3D, surface, vegetation, etc.)
            asset_id = data["id"]  # Unique identifier for the asset

            # Construct the asset's directory path
            asset_path = Path(library_path) / "Downloaded" / "/".join(data["path"])

            # Get the path to the preview image (last item in the 'preview' list)
            preview_image_path = asset_path / data["preview"][-1]

            # Retrieve asset-related metadata such as textures, LODs, and formats
            asset_textures, asset_lods, asset_formats = resolve_assets(
                asset_type, asset_id, asset_path
            )

            # Create a metadata dictionary for the asset
            metadata = {
                "name": asset_name,  # Normalized asset name
                "id": asset_id,  # Unique asset identifier
                "path": asset_path.as_posix(),  # Convert path to a POSIX string
                "type": asset_type,  # Type of asset
                "formats": asset_formats,  # Supported file formats
                "lods": asset_lods,  # Level of details (LODs)
                "textures": asset_textures,  # Texture file paths
                "preview": preview_image_path.as_posix(),  # Preview image path
                "tags": data["tags"],  # Asset tags for categorization
            }

            # Store the metadata in the dictionary with a unique key format
            megascans_data[f"{asset_type}::{asset_name}::{asset_id}"] = metadata

    # Store the processed Megascans data in the node's user data
    set_user_data(kwargs, megascans_data)

    # Display a preview image as a background in the Houdini node
    Utilities.show_background_image(kwargs)

    # Dump asset information for debugging or logging purposes
    Utilities.dump_info(kwargs, megascans_data)

    # Force the Houdini node to re-cook (recompute) with updated data
    kwargs["node"].cook(force=True)


def resolve_assets(asset_type, asset_id, asset_path):
    """
    Resolves asset metadata such as textures, LODs, and formats based on asset type.

    Args:
        asset_type (str): The type of the asset (e.g., "3d", "3dplant").
        asset_id (str): Unique identifier of the asset.
        asset_path (str or Path): The directory path where the asset is stored.

    Returns:
        tuple: A tuple containing:
            - asset_textures (dict): Texture file paths.
            - asset_lods (list): Available levels of detail (LODs).
            - asset_formats (list): Supported file formats.
    """
    # Define the path to the asset's metadata JSON file
    asset_metadata_path = Path(asset_path) / f"{asset_id}.json"

    # Check if the metadata file exists before attempting to open it
    if not asset_metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {asset_metadata_path}")

    # Open and read the asset metadata JSON file
    with asset_metadata_path.open("r", encoding="utf-8") as file:
        asset_data = json.load(file)  # Load asset metadata

    # Process the asset based on its type
    if asset_type == "3d":
        # Resolve 3D asset textures, LODs, and formats
        asset_textures = resolve_3d_tx(asset_path, asset_data)
        asset_lods, asset_formats = resolve_3d(asset_path, asset_data)

    elif asset_type == "3dplant":
        # Resolve 3D plant asset textures, LODs, and formats
        asset_textures = resolve_3dplant_tx(asset_path, asset_data)
        asset_lods, asset_formats = resolve_3dplant(asset_path, asset_data)

    else:
        # Raise an error if the asset type is unsupported
        raise ValueError(f"Unsupported asset type: {asset_type}")

    return asset_textures, asset_lods, asset_formats


def resolve_3d_tx(asset_path, asset_data):
    """
    Resolves texture data for 3D assets by checking texture maps and components.

    Args:
        asset_path (str or Path): The directory path where asset textures are stored.
        asset_data (dict): Asset metadata containing texture map and component information.

    Returns:
        dict: A dictionary mapping texture names to texture details.
    """
    asset_path_obj = Path(asset_path)

    # Try resolving textures using texture maps first
    tx_dict = resolve_3d_tx_maps(asset_path_obj, asset_data.get("maps", []))
    if tx_dict:  # If texture maps are found, return early
        return tx_dict

    # Otherwise, try resolving using texture components
    return resolve_3d_tx_components(asset_path_obj, asset_data.get("components", []))


def resolve_3d_tx_maps(asset_path_obj, maps):
    """
    Resolves texture maps for 3D assets.

    Args:
        asset_path_obj (Path): The directory path where textures are stored.
        maps (list): List of texture maps from the asset metadata.

    Returns:
        dict: A dictionary mapping texture names to their corresponding paths and attributes.
    """
    tx_dict = {}

    for tx_map in maps:
        file_path = asset_path_obj / tx_map["uri"]
        if not file_path.exists():  # Skip missing files
            continue

        name = tx_map["name"]
        resolution = tx_map["resolution"]

        # Initialize texture entry if it doesn't exist
        tx_dict.setdefault(
            name,
            {
                "type": tx_map["type"],
                "colorSpace": tx_map["colorSpace"],
                "resolution": {},
            },
        )

        # Store texture paths grouped by resolution
        tx_dict[name]["resolution"].setdefault(resolution, []).append(
            file_path.as_posix()
        )

    return tx_dict  # Return resolved texture dictionary


def resolve_3d_tx_components(asset_path_obj, components):
    """
    Resolves texture components for 3D assets.

    Args:
        asset_path_obj (Path): The directory path where textures are stored.
        components (list): List of texture components from the asset metadata.

    Returns:
        dict: A dictionary mapping texture component names to their details.
    """
    tx_dict = {}

    for component in components:
        texture_paths = {}

        for uri in component.get("uris", []):
            for resolution_data in uri.get("resolutions", []):
                textures = [
                    (asset_path_obj / tx_format["uri"]).as_posix()
                    for tx_format in resolution_data.get("formats", [])
                    if (asset_path_obj / tx_format["uri"]).exists()
                ]
                if textures:
                    texture_paths[resolution_data["resolution"]] = textures

        if texture_paths:
            tx_dict[component["name"]] = {
                "type": component["type"],
                "colorSpace": component["colorSpace"],
                "resolution": texture_paths,
            }

    return tx_dict


def resolve_3d(asset_path, asset_data):
    """
    Resolves mesh data for 3D assets, including LODs and file formats.

    Args:
        asset_path (str or Path): The directory path where asset files are stored.
        asset_data (dict): Asset metadata containing mesh information.

    Returns:
        tuple: A dictionary of LODs mapping to mesh paths and a list of supported formats.
    """
    mesh_dict = {}
    formats = set()

    # Determine whether the asset contains "meshes" or "models"
    key = "meshes" if asset_data.get("meshes") else "models"
    if key not in asset_data:
        return mesh_dict, list(formats)

    for mesh in asset_data[key]:
        uris = mesh.get("uris") or [mesh]  # Some meshes have multiple URIs
        for uri_data in uris:
            uri = uri_data["uri"]
            file_path = Path(asset_path) / uri

            if file_path.exists():
                # Extract LOD level from filename (e.g., high, lod0, lod1)
                lod_match = re.findall(r"(high|lod\d)", uri.lower())
                if lod_match:
                    lod = lod_match[0].upper()
                    formats.add(file_path.suffix.lstrip("."))
                    mesh_dict.setdefault(lod, []).append(file_path.as_posix())

    return mesh_dict, list(formats)


def resolve_3dplant_tx(asset_path, asset_data):
    """
    Resolves texture data for 3D plant assets.

    Args:
        asset_path (str or Path): The directory path where plant textures are stored.
        asset_data (dict): Asset metadata containing texture map information.

    Returns:
        dict: A dictionary mapping texture names to their details.
    """
    tx_dict = {}

    for tx_map in asset_data["maps"]:
        texture_paths = {}
        textures = []
        file_path = Path(asset_path) / tx_map["uri"]

        if file_path.exists():
            textures.append(file_path.as_posix())
            texture_paths.update({tx_map["resolution"]: textures})
            tx_dict.update(
                {
                    tx_map["name"]: {
                        "type": tx_map["type"],
                        "colorSpace": tx_map["colorSpace"],
                        "resolution": texture_paths,
                    }
                }
            )

    return tx_dict


def resolve_3dplant(asset_path, asset_data):
    """
    Resolves mesh data for 3D plant assets, including LODs and file formats.

    Args:
        asset_path (str or Path): The directory path where plant models are stored.
        asset_data (dict): Asset metadata containing model information.

    Returns:
        tuple: A dictionary of LODs mapping to model paths and a list of supported formats.
    """
    mesh_dict = {}
    formats = set()

    for model in asset_data["models"]:
        file_path = Path(asset_path) / model["uri"]

        if file_path.exists():
            geo = model["uri"]
            lod = geo.rsplit("_", maxsplit=1)[1].split(".")[0].upper()
            formats.add(file_path.suffix.lstrip("."))

            if lod in model["uri"].upper():
                if mesh_dict.get(lod) is None:
                    mesh_dict[lod] = []

                mesh_dict[lod].extend([file_path.as_posix()])

    return mesh_dict, list(formats)


def set_user_data(kwargs, megascans_data):
    """
    Stores Megascans asset metadata as user data in a Houdini node.

    Args:
        node (hou.Node): The Houdini node where metadata will be stored.
        megascans_data (dict): Dictionary containing Megascans asset metadata.

    Returns:
        None
    """
    # Remove existing Megascans user data if present
    node = kwargs["node"]
    node.destroyUserData("megascans_user_data", must_exist=False)

    # Store new Megascans data if available
    if megascans_data:
        user_data = json.dumps(megascans_data, indent=4)
        node.setUserData("megascans_user_data", user_data)
