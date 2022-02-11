# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Neon Species Benchmark dataset. https://github.com/weecology/NeonSpeciesBenchmark"""

import glob
import os
from typing import Any, Callable, Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import rasterio
import torch
from torch import Tensor

from .geo import VisionDataset
from .utils import download_url, extract_archive


class NEONTreeSpecies(VisionDataset):
    """neonspecies dataset

    The Weecology Lab at the University of Florida has developed a
    species prediction benchmark using data from the
    National Ecological Observatory Network `<https://idtrees.org/>`_

    dataset is a dataset for tree species classification.

    Dataset features:

    * RGB, Hyperspectral (HSI), LiDAR-derived CHM model
    * Remote sensing and field data generated by the
      `National Ecological Observatory Network (NEON) <https://data.neonscience.org/>`_
    * 0.1 - 1m resolution imagery
    * Train set contains X images
    * Test set contains X images

    Dataset format:

    * optical - three-channel RGB 200x200 geotiff at 10cm resolution
    * canopy height model - one-channel 20x20 geotiff at 1m resolution
    * hyperspectral - 369-channel 20x20 geotiff at 1m resolution at 1m resolution
    * shapefiles (.shp) containing field collected data on tree stems from
    NEON's Woody Vegetation Structure Dataset
    <https://data.neonscience.org/data-products/DP1.10098.001>

    Dataset classes:

    0. ACPE
    1. ACRU
    2. ACSA3
    3. AMLA
    4. BETUL
    5. CAGL8
    6. CATO6
    7. FAGR
    8. GOLA
    9. LITU
    10. LYLU3
    11. MAGNO
    12. NYBI
    13. NYSY
    14. OXYDE
    15. PEPA37
    16. PIEL
    17. PIPA2
    18. PINUS
    19. PITA
    20. PRSE2
    21. QUAL
    22. QUCO2
    23. QUGE2
    24. QUHE2
    25. QULA2
    26. QULA3
    27. QUMO4
    28. QUNI
    29. QURU
    30. QUERC
    31. ROPS
    32. TSCA

    If you use this dataset in your research, please cite the following paper:

    * TODO ADD ZENODO URL
    .. versionadded:: 0.2
    """

    classes = {
        "ACPE": "Acer pensylvanicum L.",
        "ACRU": "Acer rubrum L.",
        "ACSA3": "Acer saccharum Marshall",
        "AMLA": "Amelanchier laevis Wiegand",
        "BETUL": "Betula sp.",
        "CAGL8": "Carya glabra (Mill.) Sweet",
        "CATO6": "Carya tomentosa (Lam.) Nutt.",
        "FAGR": "Fagus grandifolia Ehrh.",
        "GOLA": "Gordonia lasianthus (L.) Ellis",
        "LITU": "Liriodendron tulipifera L.",
        "LYLU3": "Lyonia lucida (Lam.) K. Koch",
        "MAGNO": "Magnolia sp.",
        "NYBI": "Nyssa biflora Walter",
        "NYSY": "Nyssa sylvatica Marshall",
        "OXYDE": "Oxydendrum sp.",
        "PEPA37": "Persea palustris (Raf.) Sarg.",
        "PIEL": "Pinus elliottii Engelm.",
        "PIPA2": "Pinus palustris Mill.",
        "PINUS": "Pinus sp.",
        "PITA": "Pinus taeda L.",
        "PRSE2": "Prunus serotina Ehrh.",
        "QUAL": "Quercus alba L.",
        "QUCO2": "Quercus coccinea",
        "QUGE2": "Quercus geminata Small",
        "QUHE2": "Quercus hemisphaerica W. Bartram ex Willd.",
        "QULA2": "Quercus laevis Walter",
        "QULA3": "Quercus laurifolia Michx.",
        "QUMO4": "Quercus montana Willd.",
        "QUNI": "Quercus nigra L.",
        "QURU": "Quercus rubra L.",
        "QUERC": "Quercus sp.",
        "ROPS": "Robinia pseudoacacia L.",
        "TSCA": "Tsuga canadensis (L.) Carriere",
    }
    metadata = {
        "train": {
            # temp use dropbox url
            "url": "https://www.dropbox.com/sh/7hvacwqevxjxaa3/AAB9I-7NME-A7U2MBVyy_G3pa?dl=1",  # noqa: E501
            "md5": None,
            "filename": "train.zip",
        },
        "test": {
            "url": "https://www.dropbox.com/sh/iex5iy1czal5vlp/AAC174ERqPNhNyVWCrTz3wp8a?dl=1",  # noqa: E501
            "md5": None,
            "filename": "test.zip",
        },
    }
    directories = {"train": ["train"], "test": ["test"]}

    def __init__(
        self,
        root: str = "data",
        split: str = "train",
        transforms: Optional[Callable[[Dict[str, Tensor]], Dict[str, Tensor]]] = None,
        download: bool = False,
        checksum: bool = False,
    ) -> None:
        """Initialize a new dataset instance.

        Args:
            root: root directory where dataset can be found
            split: one of "train" or "test"
            transforms: a function/transform that takes input sample and its target as
                entry and returns a transformed version
            download: if True, download dataset and store it in the root directory
            checksum: if True, check the MD5 of the downloaded files (may be slow)

        Raises:
            ImportError: if laspy or pandas are are not installed
        """
        assert split in ["train", "test"]
        self.root = root
        self.split = split
        self.transforms = transforms
        self.download = download
        self.checksum = checksum
        self.class2idx = {c: i for i, c in enumerate(self.classes)}
        self.idx2class = {i: c for i, c in enumerate(self.classes)}
        self.num_classes = len(self.classes)
        self._verify()

        try:
            import geopandas as gpd  # noqa: F401
        except ImportError:
            raise ImportError(
                "geopandas is not installed and is required to use this dataset"
            )

        self.data, self.labels, self.metadata = self._load(root)

    def __getitem__(self, index: int) -> Dict[str, Tensor]:
        """Return an index within the dataset.

        Args:
            index: index to return

        Returns:
            data and label at that index
        """
        path = self.data["RGB"][index]
        image = self._load_image(path).to(torch.uint8)  # type:ignore[attr-defined]
        hsi = self._load_image(path.replace("RGB", "HSI"))
        chm = self._load_image(path.replace("RGB", "CHM"))
        metadata = self.metadata.iloc[0]

        sample = {"image": image, "hsi": hsi, "chm": chm, "metadata": metadata}

        if self.split == "train":
            sample["label"] = self.labels.label[index]

        if self.transforms is not None:
            sample = self.transforms(sample)

        return sample

    def __len__(self) -> int:
        """Return the number of data points in the dataset.

        Returns:
            length of the dataset
        """
        return len(self.data["RGB"])

    def _load_image(self, path: str) -> Tensor:
        """Load a tiff file.

        Args:
            path: path to .tif file

        Returns:
            the image
        """
        with rasterio.open(path) as f:
            array = f.read()
        tensor: Tensor = torch.from_numpy(array)  # type: ignore[attr-defined]
        return tensor

    def _load(self, root: str) -> Tuple[List[str], Dict[int, Dict[str, Any]], Any]:
        """Load files, geometries, and labels.

        Args:
            root: root directory

        Returns:
            the image path, geometries, and labels
        """
        import pandas as pd

        if self.split == "train":
            directory = os.path.join(root, self.directories[self.split][0])
            labels: pd.DataFrame = self._load_labels(directory)
        else:
            directory = root
            labels = None

        RGB_images = glob.glob(os.path.join(directory, "RGB", "*.tif"))
        CHM_images = glob.glob(os.path.join(directory, "CHM", "*.tif"))
        HSI_images = glob.glob(os.path.join(directory, "HSI", "*.tif"))
        data = {}

        data["RGB"] = RGB_images
        data["CHM"] = CHM_images
        data["HSI"] = HSI_images

        metadata = labels

        return data, labels, metadata  # type: ignore[return-value]

    def _load_labels(self, directory: str) -> Any:
        """Load the csv files containing the labels.

        Args:
            directory: directory containing shp files

        Returns:
            a pandas DataFrame containing the labels for each image
        """
        import geopandas as gpd
        path = os.path.join(directory, "label.shp")
        gdf = gpd.read_file(path)

        return gdf

    def _verify(self) -> None:
        """Verify the integrity of the dataset.

        Raises:
            RuntimeError: if ``download=False`` but dataset is missing or checksum fails
        """
        url = self.metadata[self.split]["url"]
        md5 = self.metadata[self.split]["md5"]
        filename = self.metadata[self.split]["filename"]
        directories = self.directories[self.split]

        # Check if the files already exist
        exists = [
            os.path.exists(os.path.join(self.root, directory))
            for directory in directories
        ]
        if all(exists):
            return

        # Check if zip file already exists (if so then extract)
        filepath = os.path.join(self.root, filename)
        if os.path.exists(filepath):
            extract_archive(filepath, "{}/{}".format(self.root, self.split))
            return

        # Check if the user requested to download the dataset
        if not self.download:
            raise RuntimeError(
                "Dataset not found in `root` directory and `download=False`, "
                "either specify a different `root` directory or use `download=True` "
                "to automaticaly download the dataset."
            )

        # Download and extract the dataset
        download_url(
            url, self.root, filename=filename, md5=md5 if self.checksum else None
        )
        filepath = os.path.join(self.root, filename)
        extract_archive(filepath, dst="{}/{}".format(self.root, self.split))

    def plot(
        self,
        sample: Dict[str, Tensor],
        show_titles: bool = True,
        suptitle: Optional[str] = None,
        hsi_indices: Tuple[int, int, int] = (55, 111, 170),
    ) -> plt.Figure:
        """Plot a sample from the dataset.

        Args:
            sample: a sample returned by :meth:`__getitem__`
            show_titles: flag indicating whether to show titles above each panel
            suptitle: optional string to use as a suptitle
            hsi_indices: tuple of indices to create HSI false color image

        Returns:
            a matplotlib Figure with the rendered sample
        """
        assert len(hsi_indices) == 3

        def normalize(x: Tensor) -> Tensor:
            return (x - x.min()) / (x.max() - x.min())

        ncols = 3
        hsi = normalize(sample["hsi"][hsi_indices, :, :]).permute((1, 2, 0)).numpy()
        chm = normalize(sample["chm"]).permute((1, 2, 0)).numpy()
        image = sample["image"].permute((1, 2, 0)).numpy()
        fig, axs = plt.subplots(ncols=ncols, figsize=(ncols * 10, 10))
        axs[0].imshow(image)
        axs[0].axis("off")
        axs[1].imshow(hsi)
        axs[1].axis("off")
        axs[2].imshow(chm)
        axs[2].axis("off")

        if show_titles:
            axs[0].set_title("RGB")
            axs[1].set_title("Hyperspectral False Color Image")
            axs[2].set_title("Canopy Height Model")
            if ncols > 3:
                axs[3].set_title("Predictions")

        if suptitle is not None:
            plt.suptitle(suptitle)

        return fig
