// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

library VersionTypes {
    struct MetadataDto {
        string name; // human-readable name of the facet
        bytes20 commit; // git commit hash of the deployed facet version
    }

    struct Metadata {
        address facetAddress;
        bytes20 commit; // git commit hash of the deployed facet version
    }
}
