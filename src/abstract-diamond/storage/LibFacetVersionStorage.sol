// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {VersionTypes} from "src/abstract-diamond/domain/VersionTypes.sol";

/// @notice Library providing storage helpers for facet version metadata
library LibFacetVersionStorage {
    struct Layout {
        mapping(bytes32 => VersionTypes.Metadata) facetVersions;
    }

    bytes32 internal constant STORAGE_POSITION =
        keccak256("diamond.standard.diamond.storage.facetVersion");

    event FacetVersionUpdated(
        bytes32 indexed facetId,
        string name,
        bytes20 commit
    );

    /// @notice Returns the storage layout for facet version data
    function getLayout() internal pure returns (Layout storage l) {
        bytes32 position = STORAGE_POSITION;
        assembly {
            l.slot := position
        }
    }

    /// @notice Persists a new semantic version tuple for the provided facet identifier
    function setFacetVersionByAddress(
        address facet,
        VersionTypes.MetadataDto memory metadata
    ) internal {
        bytes32 canonicalId = facetIdForName(metadata.name);

        Layout storage l = getLayout();
        VersionTypes.Metadata storage versionMetadata = l.facetVersions[
            canonicalId
        ];

        versionMetadata.facetAddress = facet;
        versionMetadata.commit = metadata.commit;

        emit FacetVersionUpdated(
            canonicalId,
            metadata.name,
            metadata.commit
        );
    }

    /// @notice Reads the stored version metadata for the provided facet identifier
    function getFacetMetadata(
        string memory facetName
    ) internal view returns (VersionTypes.Metadata memory) {
        Layout storage l = getLayout();
        return l.facetVersions[facetIdForName(facetName)];
    }

    /// @notice Utility helper for constructing a facet identifier from its name
    function facetIdForName(
        string memory name
    ) internal pure returns (bytes32 id) {
        assembly {
            id := keccak256(add(name, 0x20), mload(name))
        }
    }
}
